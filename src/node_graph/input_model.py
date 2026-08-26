"""Make a Pydantic model the wire contract of a task.

``@task(input_model=M)`` builds the task's input sockets from ``M`` and
enforces ``M`` at three moments. The body keeps a plain-Python signature and
receives plain Python: ``M`` decides types, defaults and cross-field rules;
the signature only names the parameters.

Three checkpoints, three questions:

- **wiring** (:func:`validate_wiring_inputs`): every value written at the call
  that is not a socket reference must satisfy the field it is written to. A
  reference passes untouched -- what flows through it is not known yet. The
  model runs as a flat shadow, so a field's *type* is checked and the model's
  own ``@field_validator``/``@model_validator`` are not.
- **graph expansion** (:func:`validate_graph_inputs`): a ``@task.graph``'s
  inputs are resolved by then, so the real model runs, cross-field rules
  included. The body still receives the original tagged values, because
  validation builds fresh objects and a fresh object draws no link.
- **run edge** (:func:`validated_callable`): a leaf task's inputs are
  validated once the engine has assembled and deserialized them, and the body
  receives the rich objects ``M`` declares.

At the last two, validation may change a value's *representation* and never
its *content* (:func:`check_content_invariance`): a model that derives or
rewrites an input is refused, because the derived value would reach the body
while storage and provenance keep the value the caller wrote.

Storage is the engine adapter's business, but the rendering is the model's:
:func:`model_dumper_for_socket` resolves a socket's path through the model
tree and returns the function that renders that leaf.

A mapping whose size is decided at runtime is written as a typed container
field, ``dict[str, T]``: it becomes a dynamic namespace whose members are
sockets named by the mapping's keys, each shaped by ``T``. ``extra='allow'``
is refused -- a model that admits fields it does not declare is not a
contract.
"""

from __future__ import annotations

import functools
import inspect
from dataclasses import replace
from typing import (
    Annotated,
    Any,
    Callable,
    Dict,
    List,
    Literal,
    Optional,
    Tuple,
    Type,
    cast,
    get_args,
    get_origin,
)

from pydantic import BaseModel, ValidationError, WrapValidator, create_model

__all__ = [
    "ModelContractError",
    "ModelDerivedValueError",
    "TaskInputValidationError",
    "TaskOutputValidationError",
    "apply_models",
    "check_content_invariance",
    "check_signature_against_model",
    "dump_model_field",
    "input_model_of_callable",
    "model_dumper_for_socket",
    "spec_from_model",
    "validate_graph_inputs",
    "validate_wiring_inputs",
    "validated_callable",
]

#: Attributes under which a callable carries the models its task enforces.
INPUT_MODEL_ATTR = "__node_graph_input_model__"
OUTPUT_MODEL_ATTR = "__node_graph_output_model__"

#: Attribute caching a task's input model, so the executor is resolved once.
_TASK_MODEL_CACHE = "_node_graph_cached_input_model"

#: Sentinel telling "no model" apart from "not looked up yet".
_UNRESOLVED = object()

#: How deep a generic annotation is rebuilt before it is taken as a leaf.
_MAX_ANNOTATION_DEPTH = 6

#: ``Optional[T]``'s second argument, which stands for itself in a rebuild.
_NONE_TYPE = type(None)


class ModelContractError(TypeError):
    """Raised when a model and the function it describes disagree."""


class TaskInputValidationError(ValueError):
    """Raised when a task's assembled inputs fail its input model."""


class TaskOutputValidationError(ValueError):
    """Raised when a task's return value fails its output model."""


class ModelDerivedValueError(ValueError):
    """Raised when validating an input changes its content."""


def _is_model(obj: Any) -> bool:
    return isinstance(obj, type) and issubclass(obj, BaseModel)


# --------------------------------------------------------------------------
# The socket spec a model describes
# --------------------------------------------------------------------------


def _socket_api(api: Any = None) -> Any:
    """Return the ``SocketSpecAPI`` building the spec, node-graph's by default."""
    if api is not None:
        return api
    from node_graph.socket_spec import SocketSpecAPI

    return SocketSpecAPI


def _strip_structured_types(spec: Any) -> Any:
    """Drop the ``structured_type`` descriptor from every socket in ``spec``.

    The descriptor names a class by dotted import path and is persisted with
    the task, so a class that moves or is renamed breaks stored data. Under a
    model contract nothing needs it: the model reconstructs rich values at the
    run edge, and the model itself is reached through the task's executor
    rather than through a path recorded in the data.
    """
    meta = spec.meta
    if "structured_type" in (meta.extras or {}):
        extras = dict(meta.extras)
        extras.pop("structured_type")
        spec = replace(spec, meta=replace(meta, extras=extras))
    if spec.fields:
        spec = replace(
            spec,
            fields={
                name: _strip_structured_types(child)
                for name, child in spec.fields.items()
            },
        )
    if spec.item is not None:
        spec = replace(spec, item=_strip_structured_types(spec.item))
    return spec


def _strip_optional_type(annotation: Any) -> Any:
    from node_graph.socket_spec import _strip_optional

    return _strip_optional(annotation)


def _container_item_type(annotation: Any) -> Any:
    """Return the value type of a ``dict[str, T]`` field, else ``None``.

    A bare ``dict`` names no value type and stays a leaf. ``list[T]`` is not a
    container in this sense: a namespace addresses its members by name, and a
    list has none to give.
    """
    base = _strip_optional_type(annotation)
    if get_origin(base) is not dict:
        return None
    args = get_args(base)
    if not args:
        return None
    key_type, item_type = args
    if key_type not in (str, Any):
        raise ModelContractError(
            f"A dynamic field is keyed by socket name, so its keys must be str; got {key_type!r}.\n"
            "How to fix: declare the field as dict[str, ...]."
        )
    return item_type


def _model_of_type(annotation: Any) -> Optional[Type[BaseModel]]:
    """Return the model an annotation resolves to, if it resolves to one."""
    base = _strip_optional_type(annotation)
    return base if _is_model(base) else None


def _fields_from_model(model: Type[BaseModel], spec: Any, api: Any) -> Any:
    """Overlay on ``spec`` what the model knows and ``from_model`` does not.

    Three things: a field's requiredness, which ``from_model`` leaves at
    ``True`` whatever the field's default; a default rendered JSON-safe,
    because the spec is stored with the task; and a ``dict[str, T]`` field
    turned into a typed dynamic namespace, so each key of the mapping is a
    socket of its own and can be linked by name.
    """
    fields = dict(spec.fields or {})
    for name, field in model.model_fields.items():
        child = fields.get(name)
        if child is None:
            continue
        item_type = _container_item_type(field.annotation)
        if item_type is not None:
            child = api.dynamic(item_type)
            item_model = _model_of_type(item_type)
            if item_model is not None and child.item is not None:
                child = replace(
                    child, item=_fields_from_model(item_model, child.item, api)
                )
        else:
            nested = _model_of_type(field.annotation)
            if nested is not None and child.is_namespace():
                child = _fields_from_model(nested, child, api)
        child = replace(child, meta=replace(child.meta, required=field.is_required()))
        if not field.is_required() and not child.is_namespace():
            child = replace(
                child,
                default=dump_model_field(
                    model, name, field.get_default(call_default_factory=True)
                ),
            )
        fields[name] = child
    return replace(spec, fields=fields)


def spec_from_model(model: Type[BaseModel], api: Any = None) -> Any:
    """Return the socket namespace ``model`` describes.

    An open-topped model is refused: ``extra='allow'`` accepts fields nothing
    declared, which is the one shape a contract cannot describe. A mapping
    whose size is only known at runtime is written as a typed container field,
    ``dict[str, T]``.
    """
    api = _socket_api(api)
    if model.model_config.get("extra") == "allow":
        raise ModelContractError(
            f"{model.__name__} sets extra='allow', which declares no contract for the fields it admits.\n"
            "How to fix: declare the dynamic part as a field of type dict[str, T]."
        )
    return _strip_structured_types(
        _fields_from_model(model, api.from_model(model), api)
    )


# --------------------------------------------------------------------------
# The model and the function it describes
# --------------------------------------------------------------------------


def _annotations_agree(declared: Any, annotation: Any) -> bool:
    """Return True when a signature annotation may stand for a field's type."""
    if annotation is inspect.Parameter.empty or annotation is Any:
        return True
    return bool(annotation == declared)


def check_signature_against_model(
    func: Callable[..., Any],
    model: Type[BaseModel],
    *,
    role: str,
) -> None:
    """Raise unless every field of ``model`` names a parameter of ``func``.

    ``role`` is ``'input'`` or ``'output'``; an output model is checked only
    for the shape a model may take, since it describes the return value rather
    than parameters.
    """
    name = getattr(func, "__name__", repr(func))
    if not _is_model(model):
        raise ModelContractError(
            f"{role}_model for '{name}' must be a pydantic BaseModel subclass; got {model!r}."
        )
    if role == "output":
        return

    signature = inspect.signature(func)
    for parameter in signature.parameters.values():
        if parameter.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            raise ModelContractError(
                f"'{name}' takes {parameter.name} as *args/**kwargs, which no model field can name.\n"
                f"How to fix: list the parameters explicitly, one per field of {model.__name__}."
            )
        if parameter.kind is inspect.Parameter.POSITIONAL_ONLY:
            raise ModelContractError(
                f"Parameter '{parameter.name}' of '{name}' is positional-only; a model field is passed by name.\n"
                "How to fix: move it after the / marker, or drop the marker."
            )

    parameters = dict(signature.parameters)
    declared = model.model_fields

    unnamed = [field for field in declared if field not in parameters]
    if unnamed:
        raise ModelContractError(
            f"{model.__name__} declares {', '.join(repr(f) for f in unnamed)}, which '{name}' does not take.\n"
            f"How to fix: add the parameter(s) to {name}, or remove the field(s) from {model.__name__}."
        )

    uncovered = [parameter for parameter in parameters if parameter not in declared]
    if uncovered:
        raise ModelContractError(
            f"'{name}' takes {', '.join(repr(p) for p in uncovered)}, which {model.__name__} does not declare.\n"
            f"How to fix: add the field(s) to {model.__name__}, or remove the parameter(s) from {name}."
        )

    defaulted = [
        parameter.name
        for parameter in parameters.values()
        if parameter.default is not inspect.Parameter.empty
    ]
    if defaulted:
        raise ModelContractError(
            f"'{name}' gives {', '.join(repr(p) for p in defaulted)} a default in its signature.\n"
            f"How to fix: defaults live in the model - move it to {model.__name__} and leave the parameter bare."
        )

    try:
        hints = inspect.get_annotations(func, eval_str=True)
    except Exception:
        hints = getattr(func, "__annotations__", {})
    for field_name, field in declared.items():
        annotation = hints.get(field_name, inspect.Parameter.empty)
        if not _annotations_agree(field.annotation, annotation):
            raise ModelContractError(
                f"Parameter '{field_name}' of '{name}' is annotated {annotation!r}, "
                f"but {model.__name__} declares {field.annotation!r}.\n"
                "How to fix: drop the annotation, or make it match the field."
            )


# --------------------------------------------------------------------------
# Checkpoint A -- the value written at the call
# --------------------------------------------------------------------------


def is_socket_reference(value: Any) -> bool:
    """Return True when ``value`` stands for something a link will deliver."""
    from node_graph.socket import BaseSocket, TaggedValue

    if isinstance(value, BaseSocket):
        return True
    return isinstance(value, TaggedValue) and value._socket is not None


def _accept_reference(value: Any, handler: Any, info: Any) -> Any:
    """Let a socket reference through untouched; validate anything else."""
    from node_graph.socket import TaggedValue

    if is_socket_reference(value):
        return value
    if isinstance(value, TaggedValue):
        value = value.__wrapped__
    return handler(value)


def _rebuild_generic(annotation: Any, rebuild: Callable[[Any], Any]) -> Any:
    """Return ``annotation`` with ``rebuild`` applied to each of its arguments.

    ``Literal``'s arguments are values rather than types and ``Annotated``'s
    tail is metadata, so both keep their arguments; anything else that cannot
    be rebuilt is returned unchanged.
    """
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin is None or not args:
        return None
    if origin is Literal:
        return annotation
    if origin is Annotated:
        return Annotated[tuple([rebuild(args[0]), *args[1:]])]
    try:
        return origin[
            tuple(rebuild(arg) if arg is not _NONE_TYPE else arg for arg in args)
        ]
    except TypeError:
        return annotation


def _reference_tolerant(annotation: Any, depth: int = 0) -> Any:
    """Return ``annotation`` with every level willing to hold a reference.

    Wrapping only the outermost level is not enough: a reference written into
    one member of a ``dict[str, int]`` reaches the ``int`` validator, which
    refuses it. Every level is wrapped, so a reference is accepted wherever it
    is written and every literal beside it is still checked.
    """
    if depth > _MAX_ANNOTATION_DEPTH:
        return Annotated[annotation, WrapValidator(_accept_reference)]
    rebuilt = _rebuild_generic(
        annotation, lambda arg: _reference_tolerant(arg, depth + 1)
    )
    if rebuilt is not None:
        return Annotated[rebuilt, WrapValidator(_accept_reference)]
    if _is_model(annotation):
        return Annotated[_wiring_shadow(annotation), WrapValidator(_accept_reference)]
    return Annotated[annotation, WrapValidator(_accept_reference)]


@functools.lru_cache(maxsize=None)
def _wiring_shadow(model: Type[BaseModel]) -> Type[BaseModel]:
    """Return the model checking types at the call, references included.

    The shadow is built with no base class, so the user's ``@field_validator``
    and ``@model_validator`` are left out: a rule written for whole, resolved
    inputs would otherwise be judged at wiring time against a placeholder, and
    a proxy that forwards comparisons makes that failure silent rather than
    loud.
    """
    fields = {
        name: (_reference_tolerant(field.annotation), field)
        for name, field in model.model_fields.items()
    }
    return create_model(f"{model.__name__}__Wiring", **fields)  # type: ignore[call-overload]


def validate_wiring_inputs(
    model: Type[BaseModel], inputs: Dict[str, Any], *, label: str
) -> None:
    """Raise unless every literal in ``inputs`` fits the field it is written to.

    The validated instance is discarded and ``inputs`` is passed on untouched.
    That is not tidiness: pydantic strips the proxy a tagged value wears for
    most field types, and a stripped value is a literal, so a task wired to
    the graph's input would silently become a task holding a copy of it.
    """
    try:
        _wiring_shadow(model).model_validate(inputs)
    except ValidationError as exc:
        raise TaskInputValidationError(
            f"Task '{label}' got inputs {model.__name__} rejects:\n{exc}"
        ) from exc


# --------------------------------------------------------------------------
# Validation changes representation, never content
# --------------------------------------------------------------------------


def _plain_annotation(annotation: Any, depth: int = 0) -> Any:
    """Return ``annotation`` with every model replaced by its plain twin."""
    if depth > _MAX_ANNOTATION_DEPTH:
        return annotation
    rebuilt = _rebuild_generic(
        annotation, lambda arg: _plain_annotation(arg, depth + 1)
    )
    if rebuilt is not None:
        return rebuilt
    if _is_model(annotation):
        return _plain_twin(annotation)
    return annotation


@functools.lru_cache(maxsize=None)
def _plain_twin(model: Type[BaseModel]) -> Type[BaseModel]:
    """Return ``model``'s fields with its validators and serializers left out.

    Built with no base class, so what survives is the field types and their
    constraints. Coercion is therefore identical to the model's and every rule
    the user wrote is absent, which is what makes the twin a reference for
    what the input said before any rule ran.
    """
    fields = {
        name: (_plain_annotation(field.annotation), field)
        for name, field in model.model_fields.items()
    }
    return create_model(f"{model.__name__}__Content", **fields)  # type: ignore[call-overload]


def _plain_values(value: Any) -> Any:
    """Return ``value`` with model instances turned into plain dicts.

    Field values are read as attributes rather than dumped, so a
    ``field_serializer`` -- which renders, and so is representation -- does not
    reach the comparison.
    """
    if isinstance(value, BaseModel):
        return {
            name: _plain_values(getattr(value, name))
            for name in type(value).model_fields
        }
    if isinstance(value, dict):
        return {key: _plain_values(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return type(value)(_plain_values(item) for item in value)
    return value


def _content_of(
    model: Type[BaseModel], values: Any
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Return the JSON content ``model``'s twin reads in ``values``."""
    twin = _plain_twin(model)
    try:
        instance = twin.model_validate(_plain_values(values))
    except ValidationError as exc:
        return None, str(exc)
    return instance.model_dump(mode="json", warnings=False), None


def check_content_invariance(
    model: Type[BaseModel],
    given: Dict[str, Any],
    validated: BaseModel,
    *,
    label: str,
) -> None:
    """Raise if validating ``given`` changed what any of its fields says.

    Coercion is free to change how a value is spelled -- ``'60'`` may become a
    ``Decimal`` and a list a tuple -- because both spellings carry the same
    content. Deriving a value is not: the body would then run on a value that
    never reached storage, so provenance would record one input and the body
    would have seen another. A rule that leaves an already-resolved value
    alone therefore passes, and one that rewrites it is refused.

    Only the fields ``given`` supplies are compared, so a default filling a
    field the caller omitted is not a change. Validators written into an
    annotation (``Annotated[int, AfterValidator(...)]``) are part of the type
    and run on both sides, so they are not seen here.
    """
    before, before_error = _content_of(model, given)
    after, after_error = _content_of(model, _plain_values(validated))
    if before_error is not None:
        raise ModelDerivedValueError(
            f"'{label}' cannot check what {model.__name__} did to its inputs: "
            f"the values it was given do not fit the fields they were written to.\n{before_error}\n"
            "How to fix: a validator that rewrites a value before it is checked has no reference to "
            "compare against; widen the field's type to accept what the caller writes, or derive the "
            "value before the task is built."
        )
    if after_error is not None or before is None or after is None:
        raise ModelDerivedValueError(
            f"'{label}' got values from {model.__name__} that its own fields refuse.\n{after_error}"
        )
    for name in given:
        if name not in before or name not in after:
            continue
        if before[name] != after[name]:
            raise ModelDerivedValueError(
                f"'{label}': validating input '{name}' through {model.__name__} changed it from "
                f"{before[name]!r} to {after[name]!r}.\n"
                "How to fix: validation may change how a value is spelled but not what it says. "
                "Derive the value in the outermost model, before the graph is built, and pass the "
                "derived value in."
            )


# --------------------------------------------------------------------------
# Checkpoint B -- a graph's resolved inputs
# --------------------------------------------------------------------------


def validate_graph_inputs(
    model: Type[BaseModel],
    inputs: Dict[str, Any],
    *,
    label: str,
    adapter: Any = None,
) -> None:
    """Raise unless a graph's resolved inputs satisfy ``model``.

    The graph's inputs are values by the time its body runs, so the real model
    runs here, cross-field rules included. The instance is discarded and the
    caller keeps the tagged values it had: the body turns those tags into
    links, and a fresh object carries none.

    ``adapter`` is the graph's serialization adapter, asked for the plain
    Python behind whatever the engine wrapped each value in.
    """
    from node_graph.utils import untagged_copy

    given = untagged_copy(inputs)
    if adapter is not None and hasattr(adapter, "to_python"):
        given = adapter.to_python(given)
    try:
        validated = model.model_validate(given)
    except ValidationError as exc:
        raise TaskInputValidationError(
            f"Graph '{label}' got inputs {model.__name__} rejects:\n{exc}"
        ) from exc
    check_content_invariance(model, given, validated, label=label)


# --------------------------------------------------------------------------
# Checkpoint C -- the run edge
# --------------------------------------------------------------------------


def validated_callable(
    func: Callable[..., Any],
    *,
    input_model: Optional[Type[BaseModel]] = None,
    output_model: Optional[Type[BaseModel]] = None,
    label: Optional[str] = None,
) -> Callable[..., Any]:
    """Return ``func`` wrapped so its models are enforced around every call.

    The wrapper is what the task's executor points at, so validation happens
    wherever the body runs: inputs are validated once the engine has assembled
    and deserialized them, outputs once the body has returned. The body sees
    the values the input model produced; the caller sees the JSON-safe form of
    what the output model accepted.
    """
    label = label or getattr(func, "__name__", "task")

    @functools.wraps(func)
    def call(**kwargs: Any) -> Any:
        if input_model is not None:
            try:
                validated = input_model.model_validate(kwargs)
            except ValidationError as exc:
                raise TaskInputValidationError(
                    f"Task '{label}' got inputs {input_model.__name__} rejects:\n{exc}"
                ) from exc
            check_content_invariance(input_model, kwargs, validated, label=label)
            kwargs = dict(validated)
        result = func(**kwargs)
        if output_model is not None:
            try:
                accepted = output_model.model_validate(result)
            except ValidationError as exc:
                raise TaskOutputValidationError(
                    f"Task '{label}' returned outputs {output_model.__name__} rejects:\n{exc}"
                ) from exc
            result = accepted.model_dump(mode="json")
        return result

    setattr(call, INPUT_MODEL_ATTR, input_model)
    setattr(call, OUTPUT_MODEL_ATTR, output_model)
    return call


# --------------------------------------------------------------------------
# Storage -- the model renders its own leaves
# --------------------------------------------------------------------------


def dump_model_field(model: Type[BaseModel], name: str, value: Any) -> Any:
    """Return the JSON-safe form ``model`` gives ``name``'s ``value``.

    The value is placed in an unvalidated instance and dumped through the
    model, so a ``field_serializer`` declared on ``model`` decides the stored
    form. Only ``name`` is dumped, so the other fields need not be present.
    """
    holder = model.model_construct(**{name: value})
    return holder.model_dump(mode="json", include={name}, warnings=False)[name]


def dump_model_item(model: Type[BaseModel], name: str, key: str, value: Any) -> Any:
    """Return the JSON-safe form ``model`` gives one entry of its ``name`` mapping."""
    return dump_model_field(model, name, {key: value})[key]


def input_model_of_callable(func: Any) -> Optional[Type[BaseModel]]:
    """Return the input model ``func`` enforces, if it enforces one."""
    return getattr(func, INPUT_MODEL_ATTR, None)


def output_model_of_callable(func: Any) -> Optional[Type[BaseModel]]:
    """Return the output model ``func`` enforces, if it enforces one."""
    return getattr(func, OUTPUT_MODEL_ATTR, None)


def _input_model_of_task(task: Any) -> Optional[Type[BaseModel]]:
    """Return the input model of ``task``, resolving its executor once."""
    cached = getattr(task, _TASK_MODEL_CACHE, _UNRESOLVED)
    if cached is not _UNRESOLVED:
        return cast(Optional[Type[BaseModel]], cached)
    model = None
    try:
        executor = task.spec.executor
        callable_obj = executor.callable if executor is not None else None
        callable_obj = getattr(callable_obj, "_callable", callable_obj)
        model = input_model_of_callable(callable_obj)
    except Exception:
        # A task whose executor cannot be resolved here (a pickled callable
        # restored through SafeExecutor, say) simply has no model contract to
        # apply; the generic serialization path still runs.
        model = None
    try:
        setattr(task, _TASK_MODEL_CACHE, model)
    except AttributeError:
        pass
    return model


def _dumper_for_path(
    model: Type[BaseModel], path: List[str]
) -> Optional[Callable[[Any], Any]]:
    """Return the function rendering the value at ``path`` under ``model``.

    ``path`` walks the socket names below the task's inputs. A name is a field
    of the model reached so far, except directly after a ``dict[str, T]``
    field, where it is one of the mapping's keys and the walk continues in
    ``T``. The walk ends at the model that declares the addressed value, which
    is the model whose serializers render it.
    """
    current: Optional[Type[BaseModel]] = model
    index = 0
    while current is not None and index < len(path):
        owner, name = current, path[index]
        field = owner.model_fields.get(name)
        if field is None:
            return None
        if index == len(path) - 1:
            return functools.partial(dump_model_field, owner, name)

        item_type = _container_item_type(field.annotation)
        if item_type is None:
            current = _model_of_type(field.annotation)
            index += 1
            continue
        if index + 1 == len(path) - 1:
            return functools.partial(dump_model_item, owner, name, path[index + 1])
        current = _model_of_type(item_type)
        index += 2
    return None


def model_dumper_for_socket(socket: Any) -> Optional[Callable[[Any], Any]]:
    """Return the function rendering a socket's stored value, if a model owns it.

    A socket is owned when its path resolves to a declared field, however deep
    the models and typed mappings it passes through. A socket the walk cannot
    place -- under a leaf ``dict``, say -- falls through to the generic
    serialization path, which will refuse a value it has no serializer for.
    """
    full_name = getattr(socket, "_full_name", None)
    task = getattr(socket, "_task", None)
    if not full_name or task is None:
        return None
    parts = full_name.split(".")
    if len(parts) < 2 or parts[0] != "inputs":
        return None
    model = _input_model_of_task(task)
    if model is None:
        return None
    return _dumper_for_path(model, parts[1:])


# --------------------------------------------------------------------------
# Decoration
# --------------------------------------------------------------------------


def apply_models(
    obj: Callable[..., Any],
    inputs: Any,
    outputs: Any,
    input_model: Optional[Type[BaseModel]],
    output_model: Optional[Type[BaseModel]],
    *,
    is_graph: bool = False,
    api: Any = None,
) -> Tuple[Any, Any, Callable[..., Any]]:
    """Return ``(inputs, outputs, callable)`` for a task built from models.

    Without either model this is the identity, so a task declared the usual
    way takes exactly the path it took before. A graph task keeps its own
    function as the callable -- the engine reinserts a recursion handle into
    that function's globals, which a wrapper does not carry -- and is
    validated where its inputs are resolved instead.
    """
    if input_model is None and output_model is None:
        return inputs, outputs, obj

    if not inspect.isfunction(obj) or getattr(obj, "node_class", False):
        raise ModelContractError(
            "input_model/output_model apply to a plain Python function task.\n"
            f"How to fix: drop them from {obj!r}, or wrap the process in a function task."
        )
    if input_model is not None and inputs is not None:
        raise ModelContractError(
            "'inputs' and 'input_model' both declare the input sockets.\n"
            "How to fix: keep input_model and drop inputs."
        )
    if output_model is not None and outputs is not None:
        raise ModelContractError(
            "'outputs' and 'output_model' both declare the output sockets.\n"
            "How to fix: keep output_model and drop outputs."
        )
    if is_graph and output_model is not None:
        raise ModelContractError(
            "output_model is not supported on @task.graph.\n"
            "Reason: a graph body returns socket references, which stand for values that do not exist "
            "yet, so nothing can be validated against the model.\n"
            "How to fix: put output_model on the function tasks whose outputs the graph returns."
        )

    if input_model is not None:
        check_signature_against_model(obj, input_model, role="input")
        inputs = spec_from_model(input_model, api)
    if output_model is not None:
        check_signature_against_model(obj, output_model, role="output")
        outputs = spec_from_model(output_model, api)

    if is_graph:
        # The graph body itself is the executor, so the models ride on it.
        setattr(obj, INPUT_MODEL_ATTR, input_model)
        setattr(obj, OUTPUT_MODEL_ATTR, output_model)
        return inputs, outputs, obj

    wrapped = validated_callable(
        obj, input_model=input_model, output_model=output_model
    )
    return inputs, outputs, wrapped
