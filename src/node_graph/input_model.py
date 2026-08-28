"""Make a Pydantic model the wire contract of a task.

``@task(input_model=M)`` builds the task's input sockets from ``M`` and
enforces ``M`` at three moments. The body keeps a plain-Python signature and
receives plain Python: ``M`` decides types, defaults and cross-field rules;
the signature only names the parameters.

Three checkpoints, three questions:

- **wiring** (:func:`validate_wiring_inputs`): every value written must
  satisfy the field it is written to. The model runs as a flat shadow, so a
  field's *type* is checked and a socket or a task written into an input
  passes untouched -- what flows through it is not known yet. The model's own
  ``mode='after'`` ``@field_validator``s then run over the fields whose value
  is resolved: a tagged value is judged by the value it carries, and a field
  holding a socket or a task waits. A ``@model_validator`` waits in every
  case, because it may read a field no one has written yet.
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
tree and returns the function that renders that leaf. Reading back is the
same bargain the other way round: every leaf socket records what a body
receives for it (:data:`BODY_RECEIVES`), so a field declaring a type pydantic
can rebuild from plain data arrives as plain Python, and one declaring an
engine's own data class -- or ``Any`` -- arrives as whatever the engine
stored.

A mapping whose size is decided at runtime is written as a typed container
field, ``dict[str, T]``: it becomes a dynamic namespace whose members are
sockets named by the mapping's keys, each shaped by ``T``. It is also the
only shape that carries engine data classes: a list of them is refused,
because storage keeps a list as one node of plain data. ``extra='allow'`` is
refused at any depth -- a model that admits fields it does not declare is not
a contract.
"""

from __future__ import annotations

import functools
import inspect
import sys
from copy import copy
from dataclasses import replace
from typing import (
    Annotated,
    Any,
    Callable,
    Dict,
    FrozenSet,
    List,
    Literal,
    NamedTuple,
    Optional,
    Tuple,
    Type,
    cast,
    get_args,
    get_origin,
    get_type_hints,
)

from pydantic import (
    BaseModel,
    ConfigDict,
    PlainSerializer,
    TypeAdapter,
    ValidationError,
    WrapSerializer,
    WrapValidator,
    create_model,
    field_validator,
)
from pydantic.errors import PydanticSchemaGenerationError
from pydantic_core import PydanticSerializationError
from typing_extensions import is_typeddict

__all__ = [
    "ModelContractError",
    "ModelDerivedValueError",
    "TaskInputValidationError",
    "TaskOutputValidationError",
    "BODY_RECEIVES",
    "ContentSnapshot",
    "apply_models",
    "check_content_invariance",
    "content_snapshot",
    "check_signature_against_model",
    "dump_model_field",
    "input_model_of_callable",
    "model_dumper_for_socket",
    "spec_from_model",
    "validate_graph_inputs",
    "validate_task_inputs",
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

#: Sentinel standing for a field no partial write named.
_MISSING = object()

#: How deep a generic annotation is rebuilt before it is taken as a leaf.
_MAX_ANNOTATION_DEPTH = 6

#: ``Optional[T]``'s second argument, which stands for itself in a rebuild.
_NONE_TYPE = type(None)

#: Socket extra naming what a body receives for a leaf: ``"python"`` or ``"node"``.
BODY_RECEIVES = "body_receives"

#: Container origins whose members storage flattens into one node.
_SEQUENCE_ORIGINS = (list, tuple, set, frozenset)

#: Annotation metadata that renders a value, which the content check must not see.
_SERIALIZER_METADATA = (PlainSerializer, WrapSerializer)

#: ``populate_by_name``'s replacement, on pydantic 2.11 and later.
_HAS_VALIDATE_BY_NAME = "validate_by_name" in getattr(ConfigDict, "__annotations__", {})


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


def _union_arms(annotation: Any) -> Optional[List[Any]]:
    """Return a union's arms other than ``None``, or ``None`` if it is no union."""
    from node_graph.socket_spec import _is_union_origin

    if not _is_union_origin(get_origin(annotation)):
        return None
    return [arg for arg in get_args(annotation) if arg is not _NONE_TYPE]


def _annotation_name(annotation: Any) -> str:
    """Render an annotation the way it is written."""
    if isinstance(annotation, type) and get_origin(annotation) is None:
        return annotation.__name__
    return repr(annotation)


def _plural(items: List[str], singular: str, plural: str) -> str:
    """Return the word ``items``'s number takes."""
    return singular if len(items) == 1 else plural


def _declares_any(annotation: Any) -> bool:
    """Return True when ``annotation`` is ``Any``, under an ``Optional`` or not."""
    return _strip_optional_type(annotation) is Any


def _disagreeing_kinds(
    label: str,
    subject: str,
    parts: str,
    kinds: List[Tuple[str, str]],
    *,
    declares_any: bool,
) -> ModelContractError:
    """Return the error raised when the pieces of a type arrive in both forms.

    ``kinds`` pairs each piece's rendered name with ``"python"`` or ``"node"``.
    ``declares_any`` says whether one of the pieces is ``Any``, which is worth
    naming: it is on the stored side because it declares nothing to rebuild.
    """
    rebuilt = [name for name, kind in kinds if kind == "python"]
    stored = [name for name, kind in kinds if kind == "node"]
    note = " (Any declares nothing to rebuild)" if declares_any else ""
    return ModelContractError(
        f"{label} declares {subject}, whose {parts} disagree on how the value arrives: "
        f"{', '.join(rebuilt)} {_plural(rebuilt, 'is', 'are')} rebuilt from plain data, "
        f"{', '.join(stored)} {_plural(stored, 'arrives', 'arrive')} as the engine stored "
        f"{_plural(stored, 'it', 'them')}{note}.\n"
        f"How to fix: declare {label} so its {parts} agree. A socket delivers one form, so a "
        f"value spanning both leaves nothing to decide it."
    )


def _declared_members(annotation: Any) -> Optional[List[Tuple[str, Any]]]:
    """Return the ``(name, type)`` members ``annotation`` declares, else ``None``.

    A model and a ``TypedDict`` name their members' types, and those decide
    how the value arrives: pydantic builds the mapping around an ``orm.Int``
    readily enough, and the ``orm.Int`` inside it still only an instance
    satisfies. A container is followed only as far as a member that declares
    members of its own, so ``list[int]`` is left to the plain reading below.
    """
    base = _strip_optional_type(annotation)
    if _is_model(base):
        return [(name, field.annotation) for name, field in base.model_fields.items()]
    if is_typeddict(base):
        try:
            hints = get_type_hints(base, include_extras=True)
        except Exception:
            return None
        return list(hints.items())
    origin = get_origin(base)
    if origin in _SEQUENCE_ORIGINS or origin is dict:
        args = list(get_args(base))
        if origin is dict:
            args = args[1:]
        members = [
            (f"[{index}]", arg)
            for index, arg in enumerate(args)
            if arg is not Ellipsis
            and arg is not _NONE_TYPE
            and _declared_members(arg) is not None
        ]
        return members or None
    return None


def _refuse_container_of_nodes(base: Any, label: str, depth: int) -> None:
    """Raise when a sequence's members are values only an instance satisfies.

    Storage keeps a sequence as one node holding plain data, so its members
    come back as plain data whatever they were written as. A mapping is the
    shape that survives: ``dict[str, T]`` becomes one socket, and one node,
    per key.
    """
    if get_origin(base) not in _SEQUENCE_ORIGINS:
        return
    for arg in get_args(base):
        if arg is Ellipsis or arg is _NONE_TYPE or _strip_optional_type(arg) is Any:
            continue
        if _body_receives(arg, f"{label}[]", depth + 1) != "node":
            continue
        name = _annotation_name(_strip_optional_type(arg))
        raise ModelContractError(
            f"{label} declares {_annotation_name(base)}, and a container of {name} cannot "
            f"round-trip through storage, which keeps it as one node holding plain data.\n"
            f"How to fix: declare {label} as dict[str, {name}], which gives each member a "
            f"socket and a node of its own, or as a container of plain data."
        )


def _arm_receives(annotation: Any, label: str, depth: int = 0) -> str:
    """Return ``"python"`` or ``"node"`` for one type, unions not considered."""
    base = _strip_optional_type(annotation)
    if base is Any or base is inspect.Parameter.empty:
        return "node"
    if depth <= _MAX_ANNOTATION_DEPTH:
        _refuse_container_of_nodes(base, label, depth)
        members = _declared_members(base)
        if members is not None:
            kinds = [
                (name, _body_receives(member, f"{label}.{name}", depth + 1))
                for name, member in members
            ]
            answers = {kind for _, kind in kinds}
            if len(answers) == 1:
                return answers.pop()
            raise _disagreeing_kinds(
                label,
                _annotation_name(base),
                "members",
                kinds,
                declares_any=any(_declares_any(member) for _, member in members),
            )
    try:
        TypeAdapter(annotation, config=ConfigDict(arbitrary_types_allowed=False))
    except PydanticSchemaGenerationError:
        return "node"
    except Exception:
        # A dataclass or TypedDict refuses the config argument because it
        # carries its own; each is rebuilt from plain data all the same.
        return "python"
    return "python"


def _body_receives(annotation: Any, label: str, depth: int = 0) -> str:
    """Return ``"python"`` or ``"node"`` for what a body is handed for ``annotation``.

    ``"python"`` when pydantic can build the declared type out of plain data,
    so the engine's storage wrapper has to come off before the model sees the
    value. ``"node"`` when the field can only be satisfied by an instance of a
    class pydantic treats as arbitrary -- an engine's own data class, say --
    and when the field declares ``Any``, which declares nothing to rebuild.

    A type that declares members of its own -- a nested model, a ``TypedDict``
    -- is read through them, because they are what has to be satisfied.

    A union is read one arm at a time and every arm must give the same answer.
    ``X | None`` is not a union in this sense: ``None`` is neither, so such a
    field takes ``X``'s answer. A union spanning both -- ``int | orm.Int`` --
    is refused, and so are members that disagree: a socket delivers one form,
    and nothing here can choose.
    """
    arms = _union_arms(annotation)
    if arms is None or len(arms) == 1:
        return _arm_receives(annotation if arms is None else arms[0], label, depth)
    kinds = [(arm, _arm_receives(arm, label, depth)) for arm in arms]
    answers = {kind for _, kind in kinds}
    if len(answers) == 1:
        return answers.pop()
    raise _disagreeing_kinds(
        label,
        repr(annotation),
        "arms",
        [(_annotation_name(arm), kind) for arm, kind in kinds],
        declares_any=any(_declares_any(arm) for arm, _ in kinds),
    )


def _mark_body_arrival(spec: Any, annotation: Any, label: str) -> Any:
    """Record on a leaf socket what a body receives for it.

    A namespace holds no value of its own, so only leaves are marked. The mark
    travels with the stored spec, which is what lets the read edge answer for a
    socket alone, without resolving the model behind it.
    """
    if spec.is_namespace():
        return spec
    extras = dict(spec.meta.extras or {})
    extras[BODY_RECEIVES] = _body_receives(annotation, label)
    return replace(spec, meta=replace(spec.meta, extras=extras))


def _fields_from_model(model: Type[BaseModel], spec: Any, api: Any) -> Any:
    """Overlay on ``spec`` what the model knows and ``from_model`` does not.

    Four things: a field's requiredness, which ``from_model`` leaves at
    ``True`` whatever the field's default; a default rendered JSON-safe,
    because the spec is stored with the task; a ``dict[str, T]`` field turned
    into a typed dynamic namespace, so each key of the mapping is a socket of
    its own and can be linked by name; and, on every leaf, what a body
    receives for it (:func:`_body_receives`).
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
            elif child.item is not None:
                child = replace(
                    child,
                    item=_mark_body_arrival(
                        child.item, item_type, f"{model.__name__}.{name}[]"
                    ),
                )
        else:
            nested = _model_of_type(field.annotation)
            if nested is not None and child.is_namespace():
                child = _fields_from_model(nested, child, api)
            else:
                child = _mark_body_arrival(
                    child, field.annotation, f"{model.__name__}.{name}"
                )
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


def _models_reached_by(annotation: Any, depth: int = 0) -> List[Type[BaseModel]]:
    """Return every model ``annotation`` reaches, through containers and unions."""
    if depth > _MAX_ANNOTATION_DEPTH:
        return []
    base = _strip_optional_type(annotation)
    if _is_model(base):
        return [base]
    found: List[Type[BaseModel]] = []
    for arg in get_args(base):
        found.extend(_models_reached_by(arg, depth + 1))
    return found


def _refuse_open_models(model: Type[BaseModel], seen: set, depth: int = 0) -> None:
    """Raise for any model reachable from ``model`` that admits undeclared fields.

    A nested model is checked too: a field it admits but does not declare has
    no socket, so it reaches the body without ever reaching storage.
    """
    if model in seen or depth > _MAX_ANNOTATION_DEPTH:
        return
    seen.add(model)
    if model.model_config.get("extra") == "allow":
        raise ModelContractError(
            f"{model.__name__} sets extra='allow', which declares no contract for the fields it admits.\n"
            "How to fix: declare the dynamic part as a field of type dict[str, T]."
        )
    for field in model.model_fields.values():
        for nested in _models_reached_by(field.annotation):
            _refuse_open_models(nested, seen, depth + 1)


def spec_from_model(model: Type[BaseModel], api: Any = None) -> Any:
    """Return the socket namespace ``model`` describes.

    An open-topped model is refused, at any depth: ``extra='allow'`` accepts
    fields nothing declared, which is the one shape a contract cannot
    describe. A mapping whose size is only known at runtime is written as a
    typed container field, ``dict[str, T]``.
    """
    api = _socket_api(api)
    _refuse_open_models(model, set())
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
    """Return True when ``value`` stands for something a link will deliver.

    A task counts: writing one into an input links its top-level output, so
    what arrives is decided later, exactly as for a socket. A tag does not:
    it carries the value it stands for, and that value is here now.
    """
    from node_graph.socket import BaseSocket, TaggedValue
    from node_graph.task import Task

    if isinstance(value, TaggedValue):
        value = value.__wrapped__
    return isinstance(value, (BaseSocket, Task))


def _awaits_a_link(value: Any, depth: int = 0) -> bool:
    """Return True when ``value`` holds anything a link has yet to deliver.

    A tag is looked through: it carries the value it stands for, and a value
    is what a rule can run on. A socket or a task is not -- what arrives
    through it is decided later -- and one nested anywhere inside a mapping, a
    sequence or a model instance leaves the whole value waiting. So does a
    value nested deeper than the walk goes: what has not been looked at is not
    known to have arrived.
    """
    from node_graph.socket import BaseSocket, TaggedValue
    from node_graph.task import Task

    if isinstance(value, TaggedValue):
        value = value.__wrapped__
    if isinstance(value, (BaseSocket, Task)):
        return True
    if depth > _MAX_ANNOTATION_DEPTH:
        return True
    if isinstance(value, BaseModel):
        return any(
            _awaits_a_link(getattr(value, name, None), depth + 1)
            for name in type(value).model_fields
        )
    if isinstance(value, dict):
        return any(_awaits_a_link(item, depth + 1) for item in value.values())
    if isinstance(value, _SEQUENCE_ORIGINS):
        return any(_awaits_a_link(item, depth + 1) for item in value)
    return False


def _accept_reference(value: Any, handler: Any, info: Any) -> Any:
    """Let a socket reference through untouched; validate anything else.

    The test is :func:`is_socket_reference`, the one the rule pass uses too:
    a field's type and its rules must judge the same write the same way, or a
    value one of them refuses is a value the other never sees.
    """
    from node_graph.socket import TaggedValue

    if is_socket_reference(value):
        return value
    if isinstance(value, TaggedValue):
        value = value.__wrapped__
    return handler(value)


def _accepting_instances_of(model: Type[BaseModel]) -> Callable[..., Any]:
    """Return a wrap validator that also lets an instance of ``model`` through.

    A nested field is checked against a shadow of the model it declares, and a
    shadow is a different class: pydantic would refuse the very class the field
    names. An instance already satisfies the declared type, so it passes as it
    is, wherever it is written -- alone, or inside a ``list[M]`` or
    ``dict[str, M]``.
    """

    def accept(value: Any, handler: Any, info: Any) -> Any:
        from node_graph.socket import TaggedValue

        if is_socket_reference(value):
            return value
        if isinstance(value, TaggedValue):
            value = value.__wrapped__
        if isinstance(value, model):
            return value
        return handler(value)

    return accept


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


def _accepting_field_names(config: Dict[str, Any]) -> Dict[str, Any]:
    """Return ``config`` with every field reachable by the name it is declared under."""
    config = dict(config)
    config["populate_by_name"] = True
    if _HAS_VALIDATE_BY_NAME:
        config["validate_by_name"] = True
    return config


def _shadow_config(model: Type[BaseModel]) -> ConfigDict:
    """Return the config a model rebuilt from ``model``'s fields must carry.

    ``model_config`` decides what a field accepts and how it coerces --
    whitespace stripped, a class pydantic would otherwise refuse to build a
    schema for. A rebuilt model that dropped it would judge the same value
    differently from the model it stands for.

    One key is added rather than copied: a socket is named by its field, so
    every rebuilt model accepts that name whatever alias the field carries.
    """
    return cast(ConfigDict, _accepting_field_names(dict(model.model_config)))


@functools.lru_cache(maxsize=None)
def _by_field_name(model: Type[BaseModel]) -> Type[BaseModel]:
    """Return ``model`` accepting each field under the name that names its socket.

    A field carrying ``Field(alias=...)`` is written by its alias and its
    socket is named by the field, so the model as written would refuse the
    very keys the graph delivers. The result is the model with one config key
    added -- its rules, its types, its name in an error message.
    """
    config = _accepting_field_names(dict(model.model_config))
    if config == dict(model.model_config):
        return model
    twin = type(
        model.__name__, (model,), {"model_config": ConfigDict(**config)}  # type: ignore[misc]
    )
    twin.__qualname__ = model.__qualname__
    return cast(Type[BaseModel], twin)


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
        return Annotated[
            _wiring_shadow(annotation),
            WrapValidator(_accepting_instances_of(annotation)),
        ]
    return Annotated[annotation, WrapValidator(_accept_reference)]


@functools.lru_cache(maxsize=None)
def _wiring_shadow(model: Type[BaseModel]) -> Type[BaseModel]:
    """Return the model checking types at the call, references included.

    The shadow is built with no base class, so the user's ``@field_validator``
    and ``@model_validator`` are left out: a rule written for whole, resolved
    inputs would otherwise be judged at wiring time against a placeholder, and
    a proxy that forwards comparisons makes that failure silent rather than
    loud. It keeps ``model_config``, because the config decides what a field
    accepts -- an alias reachable by field name, a class pydantic would
    otherwise refuse to build a schema for -- and a shadow that judged those
    differently would refuse calls the model accepts.
    """
    fields = {
        name: (_reference_tolerant(field.annotation), field)
        for name, field in model.model_fields.items()
    }
    return create_model(  # type: ignore[call-overload]
        f"{model.__name__}__Wiring",
        __config__=_shadow_config(model),
        **fields,
    )


def _optional_field(field: Any) -> Any:
    """Return ``field`` free to be missing, keeping its type and constraints."""
    field = copy(field)
    field.default = _MISSING
    field.default_factory = None
    field.validate_default = False
    return field


@functools.lru_cache(maxsize=None)
def _partial_wiring_shadow(model: Type[BaseModel]) -> Type[BaseModel]:
    """Return the wiring shadow with every field free to be missing.

    Inputs may be written a few at a time and a link may supply the rest, so
    a write that names some of the fields says nothing about the others. What
    it does say is checked exactly as at a call: each value against the field
    it is written to.
    """
    fields = {
        name: (_reference_tolerant(field.annotation), _optional_field(field))
        for name, field in model.model_fields.items()
    }
    return create_model(  # type: ignore[call-overload]
        f"{model.__name__}__Partial",
        __config__=_shadow_config(model),
        **fields,
    )


def _own_field_validators(model: Type[BaseModel]) -> Dict[str, Any]:
    """Return ``model``'s ``mode='after'`` field validators, ready for a twin.

    Each is taken as the model bound it, so ``cls`` inside it is still the
    class the user wrote it on, and ``check_fields`` is off because the twin
    may be handed a subset of the fields.

    Only ``mode='after'`` is taken. It judges a value the field's type has
    already accepted, which is the value every later checkpoint judges too; a
    ``before``, ``wrap`` or ``plain`` validator runs in place of that type and
    may rewrite what it is given, and a rewritten input is refused downstream
    (:func:`check_content_invariance`).
    """
    rebuilt: Dict[str, Any] = {}
    for name, decorator in model.__pydantic_decorators__.field_validators.items():
        info = decorator.info
        if info.mode != "after":
            continue
        rebuilt[name] = field_validator(*info.fields, mode="after", check_fields=False)(
            decorator.func
        )
    return rebuilt


def _write_names_of(name: str, field: Any) -> Tuple[str, ...]:
    """Return every key a write may name ``field`` by: its own name and its aliases."""
    names = [name]
    for alias in (field.alias, field.validation_alias):
        if isinstance(alias, str):
            names.append(alias)
        else:
            names.extend(
                choice
                for choice in getattr(alias, "choices", ())
                if isinstance(choice, str)
            )
    return tuple(names)


def _fields_named_by(model: Type[BaseModel], written: FrozenSet[str]) -> FrozenSet[str]:
    """Return the fields of ``model`` that ``written`` names, by name or by alias."""
    return frozenset(
        name
        for name, field in model.model_fields.items()
        if not written.isdisjoint(_write_names_of(name, field))
    )


@functools.lru_cache(maxsize=None)
def _rule_shadow(
    model: Type[BaseModel], written: FrozenSet[str]
) -> Optional[Type[BaseModel]]:
    """Return the shadow running ``model``'s rules over ``written``, or None if none apply.

    Only the named fields are built, and each keeps the annotation its model
    declares: a rule reads the value its field declares, so a nested model
    reaches it as an instance of the class the field names. A field left out
    is absent from ``info.data`` rather than standing there as a placeholder.

    ``@model_validator``s are left out: one may read a field nobody has
    written.
    """
    validators = _own_field_validators(model)
    if not validators:
        return None
    fields = {
        name: (field.annotation, _optional_field(field))
        for name, field in model.model_fields.items()
        if name in written
    }
    if not fields:
        return None
    return create_model(  # type: ignore[call-overload]
        f"{model.__name__}__Rules",
        __config__=_shadow_config(model),
        __validators__=validators,
        **fields,
    )


def _rejected_wiring(
    model: Type[BaseModel], exc: ValidationError, label: str
) -> TaskInputValidationError:
    """Return the error reporting what ``model`` refused at ``label``."""
    return TaskInputValidationError(
        f"Task '{label}' got inputs {model.__name__} rejects:\n{exc}"
    )


def validate_wiring_inputs(
    model: Type[BaseModel],
    inputs: Dict[str, Any],
    *,
    label: str,
    complete: bool = True,
) -> None:
    """Raise unless every literal in ``inputs`` fits the field it is written to.

    ``complete`` says whether ``inputs`` is the whole call, in which case a
    required field left out is refused as well.

    Types are checked first, on everything written. The model's own
    ``mode='after'`` field validators then run over the fields whose value is
    resolved; a field holding a socket or a task is checked for its shape
    alone, because what flows through it is not known yet. A rule reading a
    field nobody wrote raises ``KeyError`` from ``info.data``, and that rule
    waits for the later checkpoints, where the whole payload is in hand.

    The validated instance is discarded and ``inputs`` is passed on untouched.
    That is not tidiness: pydantic strips the proxy a tagged value wears for
    most field types, and a stripped value is a literal, so a task wired to
    the graph's input would silently become a task holding a copy of it.
    """
    from node_graph.utils import untagged_copy

    shadow = _wiring_shadow(model) if complete else _partial_wiring_shadow(model)
    try:
        shadow.model_validate(inputs)
    except ValidationError as exc:
        raise _rejected_wiring(model, exc, label) from exc
    resolved = {
        name: value for name, value in inputs.items() if not _awaits_a_link(value)
    }
    if not resolved:
        return
    rules = _rule_shadow(model, _fields_named_by(model, frozenset(resolved)))
    if rules is None:
        return
    try:
        rules.model_validate(untagged_copy(resolved))
    except ValidationError as exc:
        raise _rejected_wiring(model, exc, label) from exc
    except KeyError:
        return


def validate_task_inputs(task: Any, inputs: Dict[str, Any]) -> None:
    """Check values written into ``task``'s sockets against its input model.

    Reached by ``add_task`` and by ``set_inputs``, so a value the model
    refuses fails at the line that wrote it. Assigning to a socket's
    ``value`` writes past this check, as it does past the socket layer's own.
    A ``None`` is left out, because writing one sets nothing.
    """
    model = _input_model_of_task(task)
    if model is None:
        return
    written = {name: value for name, value in inputs.items() if value is not None}
    if written:
        validate_wiring_inputs(
            model, written, label=getattr(task, "name", "task"), complete=False
        )


# --------------------------------------------------------------------------
# Validation changes representation, never content
# --------------------------------------------------------------------------


def _plain_annotation(annotation: Any, depth: int = 0) -> Any:
    """Return ``annotation`` with every model replaced by its plain twin.

    Serializers written into the annotation (``Annotated[int,
    PlainSerializer(...)]``) are dropped along the way. They render, and a
    renderer that maps every value to the same output would hide a rewrite
    from the comparison the twin exists to make.
    """
    if depth > _MAX_ANNOTATION_DEPTH:
        return annotation
    if get_origin(annotation) is Annotated:
        args = get_args(annotation)
        inner = _plain_annotation(args[0], depth + 1)
        kept = [item for item in args[1:] if not isinstance(item, _SERIALIZER_METADATA)]
        return Annotated[tuple([inner, *kept])] if kept else inner
    rebuilt = _rebuild_generic(
        annotation, lambda arg: _plain_annotation(arg, depth + 1)
    )
    if rebuilt is not None:
        return rebuilt
    if _is_model(annotation):
        return _plain_twin(annotation)
    return annotation


def _comparable_field(field: Any) -> Any:
    """Return ``field`` with what only renders it taken off, so it is comparable.

    Two things are taken off. ``Field(exclude=True)`` keeps a field out of a
    dump, which would keep it out of the comparison too. A serializer written
    into the annotation (``Annotated[int, PlainSerializer(...)]``) lands in
    the field's metadata rather than in its type, and one that maps every
    value to the same output would hide a rewrite behind it. Both say how a
    value is rendered, not what was written.
    """
    metadata = list(getattr(field, "metadata", ()) or ())
    kept = [item for item in metadata if not isinstance(item, _SERIALIZER_METADATA)]
    if getattr(field, "exclude", None) is None and len(kept) == len(metadata):
        return field
    field = copy(field)
    field.exclude = None
    field.metadata = kept
    return field


@functools.lru_cache(maxsize=None)
def _plain_twin(model: Type[BaseModel]) -> Type[BaseModel]:
    """Return ``model``'s fields with its validators and serializers left out.

    Built with no base class, so what survives is the field types and their
    constraints, and ``model_config``, which decides how a value is coerced.
    Coercion is therefore identical to the model's and every rule the user
    wrote is absent, which is what makes the twin a reference for what the
    input said before any rule ran.
    """
    fields = {
        name: (_plain_annotation(field.annotation), _comparable_field(field))
        for name, field in model.model_fields.items()
    }
    return create_model(  # type: ignore[call-overload]
        f"{model.__name__}__Content",
        __config__=_shadow_config(model),
        **fields,
    )


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
    """Return the content ``model``'s twin reads in ``values``, field by field.

    A field is rendered as JSON, which is the form two values can be compared
    in whatever they are spelled as. A field pydantic cannot render -- an
    engine's data node or any object under ``Any`` -- keeps the object itself
    instead, so it is compared as it stands rather than aborting the check
    with a serialization error.
    """
    twin = _plain_twin(model)
    try:
        instance = twin.model_validate(_plain_values(values))
    except ValidationError as exc:
        return None, str(exc)
    content: Dict[str, Any] = {}
    for name in type(instance).model_fields:
        try:
            content[name] = instance.model_dump(
                mode="json", include={name}, warnings=False
            )[name]
        except (PydanticSerializationError, KeyError):
            content[name] = getattr(instance, name)
    return content, None


def _same_content(before: Any, after: Any) -> bool:
    """Return True when two readings of a field say the same thing.

    A field rendered as JSON compares as JSON. One kept as the object it is --
    an engine's data node, anything under ``Any`` -- may answer an inequality
    with something other than a bool: a numpy array answers with an array of
    them, which no ``if`` can read. Such a value counts as unchanged when it
    is the same object, when a whole-array comparison says so, or when the two
    render identically.
    """
    if before is after:
        return True
    try:
        return not bool(before != after)
    except (TypeError, ValueError):
        pass
    numpy = sys.modules.get("numpy")
    if (
        numpy is not None
        and isinstance(before, numpy.ndarray)
        and isinstance(after, numpy.ndarray)
    ):
        return bool(numpy.array_equal(before, after))
    return repr(before) == repr(after)


class ContentSnapshot(NamedTuple):
    """What a model's inputs said, read before any of its validators ran."""

    content: Optional[Dict[str, Any]]
    error: Optional[str]
    names: Tuple[str, ...]


def content_snapshot(model: Type[BaseModel], given: Dict[str, Any]) -> ContentSnapshot:
    """Return what ``given`` says, read before ``model`` is allowed to run.

    Taken first and kept, because a validator may rewrite the very values it
    is judged against: one that appends to a list in place, or reaches into a
    nested model instance, leaves nothing behind to compare with. Rendering
    the values to JSON here is what makes the snapshot independent of what
    happens to them afterwards.
    """
    content, error = _content_of(model, given)
    return ContentSnapshot(content, error, tuple(given))


def check_content_invariance(
    model: Type[BaseModel],
    before_snapshot: ContentSnapshot,
    validated: BaseModel,
    *,
    label: str,
) -> None:
    """Raise if validating changed what any supplied field says.

    ``before_snapshot`` comes from :func:`content_snapshot`, taken before the
    model ran. Coercion is free to change how a value is spelled -- ``'60'``
    may become a ``Decimal`` and a list a tuple -- because both spellings
    carry the same content. Deriving a value is not: the body would then run
    on a value that never reached storage, so provenance would record one
    input and the body would have seen another. A rule that leaves an
    already-resolved value alone therefore passes, and one that rewrites it is
    refused.

    Only the fields the caller supplied are compared, so a default filling a
    field the caller omitted is not a change. Validators written into an
    annotation (``Annotated[int, AfterValidator(...)]``) are part of the type
    and run on both sides of the comparison, so they must be idempotent: one
    that doubles its input is refused, because the second run doubles it
    again.

    A field the model has no JSON form for is compared as the object it is,
    which catches a rule that replaces it and not one that reaches inside it.
    """
    before, before_error, names = before_snapshot
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
    for name in names:
        if name not in before or name not in after:
            continue
        if not _same_content(before[name], after[name]):
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
) -> None:
    """Raise unless a graph's resolved inputs satisfy ``model``.

    The graph's inputs are values by the time its body runs, so the real model
    runs here, cross-field rules included. The instance is discarded and the
    caller keeps the tagged values it had: the body turns those tags into
    links, and a fresh object carries none.

    ``inputs`` arrive as the body will see them: the engine's read edge has
    already given each leaf the form its field declares.
    """
    from node_graph.utils import untagged_copy

    given = untagged_copy(inputs)
    before = content_snapshot(model, given)
    try:
        validated = _by_field_name(model).model_validate(given)
    except ValidationError as exc:
        raise TaskInputValidationError(
            f"Graph '{label}' got inputs {model.__name__} rejects:\n{exc}"
        ) from exc
    check_content_invariance(model, before, validated, label=label)


# --------------------------------------------------------------------------
# Checkpoint C -- the run edge
# --------------------------------------------------------------------------


def _dump_model_instance(instance: BaseModel) -> Dict[str, Any]:
    """Return the JSON-safe form of every field of ``instance``.

    A field the model has no JSON form for keeps the object it holds, exactly
    as :func:`dump_model_field` does on the way in, so one such output does
    not cost the whole return value its rendering.
    """
    try:
        return cast(Dict[str, Any], instance.model_dump(mode="json", warnings=False))
    except PydanticSerializationError:
        pass
    dumped: Dict[str, Any] = {}
    for name in type(instance).model_fields:
        try:
            dumped[name] = instance.model_dump(
                mode="json", include={name}, warnings=False
            )[name]
        except (PydanticSerializationError, KeyError):
            dumped[name] = getattr(instance, name)
    return dumped


def _refuse_undeclared_outputs(model: Type[BaseModel], result: Any, label: str) -> None:
    """Raise when a returned mapping carries a key ``model`` does not declare.

    The model declares the output sockets, so a key it does not name has
    nowhere to be written and would be dropped between the body and the
    task's outputs.
    """
    if not isinstance(result, dict):
        return
    declared = set()
    for name, field in model.model_fields.items():
        declared.add(name)
        for alias in (field.alias, field.validation_alias, field.serialization_alias):
            if isinstance(alias, str):
                declared.add(alias)
    undeclared = [key for key in result if key not in declared]
    if undeclared:
        raise TaskOutputValidationError(
            f"Task '{label}' returned {', '.join(repr(key) for key in undeclared)}, "
            f"which {model.__name__} does not declare.\n"
            f"How to fix: add the field(s) to {model.__name__}, or drop them from what "
            f"the body returns."
        )


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
            before = content_snapshot(input_model, kwargs)
            try:
                validated = _by_field_name(input_model).model_validate(kwargs)
            except ValidationError as exc:
                raise TaskInputValidationError(
                    f"Task '{label}' got inputs {input_model.__name__} rejects:\n{exc}"
                ) from exc
            check_content_invariance(input_model, before, validated, label=label)
            kwargs = dict(validated)
        result = func(**kwargs)
        if output_model is not None:
            _refuse_undeclared_outputs(output_model, result, label)
            try:
                accepted = _by_field_name(output_model).model_validate(result)
            except ValidationError as exc:
                raise TaskOutputValidationError(
                    f"Task '{label}' returned outputs {output_model.__name__} rejects:\n{exc}"
                ) from exc
            result = _dump_model_instance(accepted)
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

    A value the model has no JSON form for -- an engine's data node, an object
    under ``Any`` -- and a field ``Field(exclude=True)`` keeps out of a dump
    are returned as they are, for the engine's own serialization to store or
    to refuse in its own words.
    """
    holder = model.model_construct(**{name: value})
    try:
        return holder.model_dump(mode="json", include={name}, warnings=False)[name]
    except (PydanticSerializationError, KeyError):
        return value


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
