from __future__ import annotations
from dataclasses import dataclass, field, replace, MISSING
from typing import (
    Any,
    Dict,
    Optional,
    Union,
    Iterable,
    Annotated,
    get_origin,
    get_args,
    get_type_hints,
)
import inspect
from copy import deepcopy
from node_graph.orm.mapping import type_mapping as DEFAULT_TM
from .socket import NodeSocketNamespace
import ast
import textwrap

__all__ = [
    "SocketSpecMeta",
    "SocketSpec",
    "SocketView",
    "BaseSocketSpecAPI",
    "BaseSpecInferAPI",
    "socket",
    "namespace",
    "dynamic",
    "expose",
    "infer_specs_from_callable",
    "set_default",
    "unset_default",
    "merge_specs",
]

WidgetConfig = Union[str, Dict[str, Any]]


@dataclass(frozen=True)
class SocketSpecMeta:
    help: Optional[str] = None
    # by default all sockets are required
    required: Optional[bool] = True
    # "args" | "kwargs" | "var_args" | "var_kwargs" | "return"
    call_role: Optional[str] = None
    sub_socket_default_link_limit: Optional[int] = 1
    widget: Optional[WidgetConfig] = None


@dataclass(frozen=True)
class SocketSpec:
    """
    Immutable socket schema tree (leaf or namespace).

    - identifier: leaf type identifier or "node_graph.namespace"
    - dynamic: namespace accepts arbitrary keys (item gives per-key schema)
    - item: schema for each dynamic key (leaf or namespace)
    - fields: fixed fields for namespace (name -> schema)
    - default: leaf-only default value
    - meta: optional meta (help/required/widget)
    """

    identifier: str
    dynamic: bool = False
    item: Optional["SocketSpec"] = None
    default: Any = field(default_factory=lambda: MISSING)
    fields: Dict[str, "SocketSpec"] = field(default_factory=dict)
    meta: SocketSpecMeta = field(default_factory=SocketSpecMeta)

    # --- structural predicate ---
    def is_namespace(self) -> bool:
        if self.dynamic or self.fields:
            return True
        ident = self.identifier or ""
        return "namespace" in ident

    def has_default(self) -> bool:
        # only check against MISSING, and only for leaves
        return not isinstance(self.default, type(MISSING)) and (not self.is_namespace())

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"identifier": self.identifier, "dynamic": self.dynamic}
        if self.item is not None:
            d["item"] = self.item.to_dict()
        if self.fields:
            d["fields"] = {k: v.to_dict() for k, v in self.fields.items()}

        # Serialize default only for leaves and only if not MISSING
        if not self.is_namespace() and not isinstance(self.default, type(MISSING)):
            d["default"] = deepcopy(self.default)

        if any(
            getattr(self.meta, k) is not None
            for k in (
                "help",
                "required",
                "widget",
                "call_role",
                "sub_socket_default_link_limit",
            )
        ):
            d["meta"] = {
                k: getattr(self.meta, k)
                for k in (
                    "help",
                    "required",
                    "widget",
                    "call_role",
                    "sub_socket_default_link_limit",
                )
                if getattr(self.meta, k) is not None
            }
        return d

    @classmethod
    def from_dict(
        cls, d: Dict[str, Any], *, type_mapping: Optional[dict] = None
    ) -> "SocketSpec":
        meta = SocketSpecMeta(**d.get("meta", {}))
        item = (
            cls.from_dict(d["item"], type_mapping=type_mapping) if "item" in d else None
        )
        fields = {
            k: cls.from_dict(v, type_mapping=type_mapping)
            for k, v in d.get("fields", {}).items()
        }
        default = d.get("default", MISSING)
        return cls(
            identifier=d["identifier"],
            dynamic=bool(d.get("dynamic", False)),
            item=item,
            fields=fields,
            default=default,
            meta=meta,
        )

    def include(self, *names: str) -> "SocketSpec":
        _ensure_namespace(self)
        wanted = set(names)
        new_fields = {k: v for k, v in self.fields.items() if k in wanted}
        return replace(self, fields=new_fields)

    def exclude(self, *names: str) -> "SocketSpec":
        _ensure_namespace(self)
        banned = set(names)
        new_fields = {k: v for k, v in self.fields.items() if k not in banned}
        return replace(self, fields=new_fields)

    def only(self, *names: str) -> "SocketSpec":
        return self.include(*names)

    def rename(self, mapping: Dict[str, str]) -> "SocketSpec":
        _ensure_namespace(self)
        new_fields: Dict[str, SocketSpec] = {}
        for old, spec in self.fields.items():
            new = mapping.get(old, old)
            if new in new_fields:
                raise ValueError(f"rename collision: '{new}' already exists")
            new_fields[new] = spec
        return replace(self, fields=new_fields)

    def prefix(self, pfx: str) -> "SocketSpec":
        _ensure_namespace(self)
        new_fields = {f"{pfx}{k}": v for k, v in self.fields.items()}
        return replace(self, fields=new_fields)

    # --- snapshot from a live namespace (no graph dep) ---
    @classmethod
    def from_namespace(
        cls, live_ns, *, role: str = "input", type_mapping: Optional[dict] = None
    ) -> "SocketSpec":
        """Snapshot a live NodeSocketNamespace (works without a graph).
        Duck-typed to support tests (no hard import / isinstance on concrete classes).
        """
        tm = type_mapping or DEFAULT_TM

        def _iter_ns_items(ns):
            # Support both real NodeSocketNamespace (_sockets) and test fakes (sockets)
            if hasattr(ns, "_sockets") and isinstance(getattr(ns, "_sockets"), dict):
                return ns._sockets.items()
            try:
                return ns.items()  # if a raw mapping is passed
            except Exception:
                return []

        def _is_ns(obj) -> bool:
            return hasattr(obj, "_sockets") or hasattr(obj, "sockets")

        def _leaf_spec(sock) -> "SocketSpec":
            ident = (
                getattr(sock, "_identifier", None)
                or getattr(sock, "identifier", None)
                or getattr(sock, "ident", None)
                or tm.get("default", "node_graph.any")
            )
            return SocketSpec(identifier=ident)

        def _ns_spec(ns) -> "SocketSpec":
            fields: dict[str, SocketSpec] = {}
            for name, child in _iter_ns_items(ns):
                if _is_ns(child):
                    fields[name] = _ns_spec(child)
                else:
                    fields[name] = _leaf_spec(child)
            spec = SocketSpec(
                identifier=tm.get("namespace", "node_graph.namespace"), fields=fields
            )
            # best-effort dynamic flag
            md = getattr(ns, "_metadata", None)
            if md is not None and getattr(md, "dynamic", False):
                any_item = SocketSpec(
                    identifier=tm.get("any", tm.get("default", "node_graph.any"))
                )
                spec = replace(spec, dynamic=True, item=any_item)
            return spec

        return _ns_spec(live_ns)


def _unwrap_annotated(tp: Any) -> tuple[Any, Optional[SocketSpecMeta]]:
    origin = get_origin(tp)
    if origin is Annotated:
        args = list(get_args(tp))
        base = args[0]
        m = next((a for a in args[1:] if isinstance(a, SocketSpecMeta)), None)
        return base, m
    return tp, None


def _is_namespace(spec: SocketSpec) -> bool:
    return spec.is_namespace()


def _ensure_namespace(spec: SocketSpec) -> None:
    if not _is_namespace(spec):
        raise TypeError("Expose/rename/prefix require a namespace SocketSpec")


def _extract_spec_from_annotated(tp: Any) -> Optional[SocketSpec]:
    """Return a SocketSpec embedded in Annotated metadata, if present."""
    if get_origin(tp) is Annotated:
        for meta in get_args(tp)[1:]:
            if isinstance(meta, SocketView):
                return meta.to_spec()
            if isinstance(meta, SocketSpec):
                return meta
    return None


class SocketView:
    """A lightweight, pure view over a SocketSpec to chain transforms fluently."""

    __slots__ = ("_spec",)

    def __init__(self, spec: SocketSpec) -> None:
        # Set without going through normal attribute logic
        object.__setattr__(self, "_spec", spec)

    def include(self, *names: str) -> "SocketView":
        return SocketView(object.__getattribute__(self, "_spec").include(*names))

    def exclude(self, *names: str) -> "SocketView":
        return SocketView(object.__getattribute__(self, "_spec").exclude(*names))

    def only(self, *names: str) -> "SocketView":
        return self.include(*names)

    def rename(self, mapping: Dict[str, str]) -> "SocketView":
        return SocketView(object.__getattribute__(self, "_spec").rename(mapping))

    def prefix(self, pfx: str) -> "SocketView":
        return SocketView(object.__getattribute__(self, "_spec").prefix(pfx))

    def to_spec(self) -> SocketSpec:
        return object.__getattribute__(self, "_spec")

    def __getattr__(self, name: str) -> "SocketView":
        # Only called if normal attribute lookup fails
        spec: SocketSpec = object.__getattribute__(self, "_spec")
        if name == "item":
            if spec.dynamic and spec.item is not None:
                return SocketView(spec.item)
            raise AttributeError("'.item' only valid on dynamic namespace specs")
        if spec.fields and name in spec.fields:
            return SocketView(spec.fields[name])
        raise AttributeError(f"'{name}' not found in namespace spec")

    def __getitem__(self, name: str) -> "SocketView":
        return self.__getattr__(name)


class BaseSocketSpecAPI:
    """
    Class-based authoring helpers using @classmethod.
    Subclass and override TYPE_MAPPING (and optionally _map_identifier) downstream.
    """

    TYPE_MAPPING: Dict[str | Any, str] = DEFAULT_TM

    # Re-exports for convenience
    SocketSpec = SocketSpec
    SocketSpecMeta = SocketSpecMeta
    SocketView = SocketView
    SocketNamespace = NodeSocketNamespace

    @classmethod
    def socket(cls, T: Any, **meta) -> Any:
        """Wrap a type with optional metadata (help/required/widget)."""
        return Annotated[T, SocketSpecMeta(**meta)]

    @classmethod
    def namespace(cls, _name: str | None = None, /, **fields) -> SocketSpec:
        tm = cls.TYPE_MAPPING
        spec = SocketSpec(identifier=tm["namespace"])
        new_fields: Dict[str, SocketSpec] = {}

        for name, val in fields.items():
            has_default = isinstance(val, tuple) and len(val) == 2
            T, default_val = val if has_default else (val, MISSING)
            base_T, meta = _unwrap_annotated(T)
            s_meta = meta or SocketSpecMeta()

            if isinstance(base_T, SocketSpec):
                child = base_T
            elif isinstance(base_T, SocketView):
                child = base_T.to_spec()
            else:
                child = SocketSpec(identifier=cls._map_identifier(base_T), meta=s_meta)

            # Set default directly on leaf child
            if has_default:
                if child.is_namespace():
                    raise TypeError(
                        f"Default provided for namespace field '{name}'. "
                        "Provide a structured default via function signature mapping instead."
                    )
                child = replace(child, default=default_val)

            new_fields[name] = child

        return replace(spec, fields=new_fields)

    @classmethod
    def dynamic(cls, item_type: Any, /, **fixed) -> SocketSpec:
        base = cls.namespace(**fixed)
        base = replace(base, dynamic=True)
        T, meta = _unwrap_annotated(item_type)
        s_meta = meta or SocketSpecMeta()
        item_spec = (
            T
            if isinstance(T, SocketSpec)
            else SocketSpec(identifier=cls._map_identifier(T), meta=s_meta)
        )
        return replace(base, item=item_spec)

    @classmethod
    def expose(
        cls,
        spec_or_view: SocketSpec | SocketView,
        *,
        include: Iterable[str] | None = None,
        exclude: Iterable[str] | None = None,
        rename: Dict[str, str] | None = None,
        prefix: str | None = None,
    ) -> SocketSpec:
        spec = (
            spec_or_view.to_spec()
            if isinstance(spec_or_view, SocketView)
            else spec_or_view
        )
        _ensure_namespace(spec)
        if include:
            spec = spec.include(*include)
        if exclude:
            spec = spec.exclude(*exclude)
        if rename:
            spec = spec.rename(rename)
        if prefix:
            spec = spec.prefix(prefix)
        return spec

    @classmethod
    def _map_identifier(cls, tp: Any) -> str:
        tm = cls.TYPE_MAPPING
        if tp in tm:
            return tm[tp]
        origin = get_origin(tp)
        if origin in (list, tuple, set):
            return tm.get(list, tm["default"])  # list used as generic sequence
        return tm.get("default", "node_graph.any")

    @classmethod
    def validate_socket_data(cls, data: SocketSpec | list | None) -> SocketSpec | None:
        """Validate socket data and convert it to a dictionary.
        If data is None, return an empty dictionary.
        If data is a list, convert it to a dictionary with empty dictionaries as values.
        """

        if data is None or isinstance(data, SocketSpec):
            return data
        elif isinstance(data, SocketView):
            return data.to_spec()
        elif isinstance(data, list):
            if not all(isinstance(d, str) for d in data):
                raise TypeError("All elements in the list must be strings")
            return cls.namespace(**{d: Any for d in data})
        else:
            raise TypeError(
                f"Expected list or namespace type, got {type(data).__name__}"
            )


class BaseSpecInferAPI:
    """Strict inference: no structural guessing into namespaces.

    - Only explicit SocketSpec / SocketView(.to_spec()) can create namespaces.
    - VAR_POSITIONAL / VAR_KEYWORD produce dynamic namespaces (by signature),
      with item type taken from Annotated[T, ...] if provided, else Any.
    """

    TYPE_MAPPING: Dict[str | Any, str] = DEFAULT_TM
    DEFAULT_OUTPUT_KEY: str = "result"  # allow downstream override

    @classmethod
    def _map_identifier(cls, tp: Any) -> str:
        tm = cls.TYPE_MAPPING
        if tp in tm:
            return tm[tp]
        origin = get_origin(tp)
        if origin in (list, tuple, set):
            return tm.get(list, tm["default"])
        return tm.get("default", "node_graph.any")

    @staticmethod
    def _safe_type_hints(func):
        try:
            return get_type_hints(func, include_extras=True)
        except TypeError:
            return get_type_hints(func)

    @staticmethod
    def _is_namespace(spec: SocketSpec) -> bool:
        return bool(spec.dynamic or spec.fields)

    @classmethod
    def _apply_structured_defaults_to_leaves(
        cls, ns_spec: SocketSpec, dv: dict[str, Any]
    ) -> SocketSpec:
        """
        Recursively apply dict defaults by setting defaults on leaf specs only.
        """
        if not cls._is_namespace(ns_spec):
            # If a dict was supplied but spec isn’t a namespace, ignore silently.
            return ns_spec

        new_fields: dict[str, SocketSpec] = {}
        for k, child in (ns_spec.fields or {}).items():
            if k not in dv:
                new_fields[k] = child
                continue
            val = dv[k]
            if isinstance(val, dict) and cls._is_namespace(child):
                # Traverse deeper
                new_fields[k] = cls._apply_structured_defaults_to_leaves(child, val)
            else:
                # Scalar default -> must land on a leaf spec
                if child.is_namespace():
                    raise TypeError(
                        f"Default for '{k}' is scalar, but the field is a namespace."
                    )
                new_fields[k] = replace(child, default=val)
        return replace(ns_spec, fields=new_fields)

    @classmethod
    def _spec_from_annotation(cls, T: Any) -> SocketSpec:
        """Only returns a leaf (or passes through explicit SocketSpec/.to_spec())."""
        if hasattr(T, "to_spec") and callable(getattr(T, "to_spec")):
            return T.to_spec()

        base_T, meta = _unwrap_annotated(T)
        meta = meta or SocketSpecMeta()

        # Already a SocketSpec
        if isinstance(base_T, SocketSpec):
            return base_T

        # No dataclass / TypedDict / __annotations__ expansion here anymore.
        return SocketSpec(identifier=cls._map_identifier(base_T), meta=meta)

    @classmethod
    def build_inputs_from_signature(
        cls, func, explicit: SocketSpec | None = None
    ) -> SocketSpec:
        """Always return a NAMESPACE spec (possibly empty).
        - POSITIONAL_ONLY -> call_role="args"
        - POSITIONAL_OR_KEYWORD / KEYWORD_ONLY -> call_role="kwargs"
        - *args -> dynamic namespace of item T, call_role="var_args"
        - **kwargs -> dynamic namespace of item T, call_role="var_kwargs"

        """
        if explicit is not None:
            if not isinstance(explicit, SocketSpec):
                raise TypeError("inputs must be a SocketSpec (namespace/dynamic)")
            if not cls._is_namespace(explicit):
                # wrap a leaf into a namespace field named after the parameter is ambiguous;
                # require explicit namespaces for inputs to avoid surprises
                raise TypeError("inputs must be a namespace (use `namespace(...)`).")
            return explicit

        sig = inspect.signature(func)
        ann_map = cls._safe_type_hints(func)

        fields: dict[str, SocketSpec] = {}
        # if var_args or var_kwargs are present, the top level becomes dynamic
        is_dyn: bool = False

        for name, param in sig.parameters.items():
            T = ann_map.get(name, param.annotation)
            base_T, meta = _unwrap_annotated(T)
            meta = meta or SocketSpecMeta()

            # Determine call_role
            if param.kind is inspect.Parameter.POSITIONAL_ONLY:
                call_role = "args"
            elif param.kind is inspect.Parameter.VAR_POSITIONAL:
                call_role = "var_args"
                is_dyn = True
            elif param.kind is inspect.Parameter.VAR_KEYWORD:
                call_role = "var_kwargs"
                is_dyn = True
            else:
                call_role = "kwargs"
            if meta.call_role is None:
                meta = replace(meta, call_role=call_role)

            # Determine required
            is_required = not (
                param.default is not inspect._empty
                or param.kind
                in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
            )
            meta = replace(meta, required=is_required)

            # Prefer spec from Annotated metadata if present
            annotated_spec = _extract_spec_from_annotated(T)
            if annotated_spec is not None:
                spec = annotated_spec
            else:
                spec = cls._spec_from_annotation(base_T)

            # Merge meta (user's meta has priority over derived)
            merged = SocketSpecMeta(
                help=spec.meta.help if spec.meta.help is not None else meta.help,
                required=meta.required
                if meta.required is not None
                else spec.meta.required,
                widget=spec.meta.widget
                if spec.meta.widget is not None
                else meta.widget,
                call_role=meta.call_role
                if meta.call_role is not None
                else spec.meta.call_role,
            )
            spec = replace(spec, meta=merged)

            # varargs/kwargs become dynamic namespaces
            if param.kind is inspect.Parameter.VAR_POSITIONAL:
                item_T, _ = _unwrap_annotated(T)
                item_spec = cls._spec_from_annotation(
                    item_T if item_T is not inspect._empty else Any
                )
                spec = SocketSpec(
                    identifier=cls.TYPE_MAPPING["namespace"],
                    dynamic=True,
                    item=item_spec,
                    meta=spec.meta,
                )
            elif param.kind is inspect.Parameter.VAR_KEYWORD:
                item_T, _ = _unwrap_annotated(T)
                item_spec = cls._spec_from_annotation(
                    item_T if item_T is not inspect._empty else Any
                )
                spec = SocketSpec(
                    identifier=cls.TYPE_MAPPING["namespace"],
                    dynamic=True,
                    item=item_spec,
                    meta=spec.meta,
                )

            # Defaults: scalar -> leaf default; dict -> traverse into leaves
            if param.default is not inspect._empty and param.default is not None:
                if isinstance(param.default, dict) and cls._is_namespace(spec):
                    spec = cls._apply_structured_defaults_to_leaves(spec, param.default)
                else:
                    if spec.is_namespace():
                        raise TypeError(
                            f"Scalar default provided for namespace parameter '{name}'. "
                            "Use a structured mapping of defaults."
                        )
                    spec = replace(spec, default=param.default)

            fields[name] = spec

        # Always return a namespace, even if empty
        return SocketSpec(
            identifier=cls.TYPE_MAPPING["namespace"],
            fields=fields,
            dynamic=is_dyn,
            meta=SocketSpecMeta(call_role="kwargs"),
        )

    @classmethod
    def build_outputs_from_signature(
        cls, func, explicit: SocketSpec | None
    ) -> SocketSpec:
        """Always return a NAMESPACE spec, but:
        - If the function body never does `return <value>`, return an EMPTY namespace,
        regardless of annotations.
        - Otherwise, honor explicit, Annotated, or wrap leaf under DEFAULT_OUTPUT_KEY.
        """
        import inspect

        def _wrap_leaf_as_ns(leaf: SocketSpec) -> SocketSpec:
            return SocketSpec(
                identifier=cls.TYPE_MAPPING["namespace"],
                fields={cls.DEFAULT_OUTPUT_KEY: leaf},
                meta=SocketSpecMeta(call_role="return"),
            )

        if explicit is not None:
            if isinstance(explicit, SocketView):
                explicit = explicit.to_spec()
            if not isinstance(explicit, SocketSpec):
                raise TypeError("outputs must be a SocketSpec")
            # Respect namespaces (even empty) as-is; just set call_role
            if cls._is_namespace(explicit):
                return replace(explicit, meta=SocketSpecMeta(call_role="return"))
            return _wrap_leaf_as_ns(explicit)

        # If function body never returns a value -> EMPTY namespace (no 'result')
        if not _function_returns_value(func):
            return SocketSpec(
                identifier=cls.TYPE_MAPPING["namespace"],
                fields={},  # empty
                dynamic=False,
                meta=SocketSpecMeta(call_role="return"),
            )

        # Otherwise, infer from return annotation / metadata
        ann_map = cls._safe_type_hints(func)
        ret = ann_map.get("return", None)

        spec_from_meta = _extract_spec_from_annotated(ret)
        if spec_from_meta is not None:
            return replace(
                spec_from_meta, meta=replace(spec_from_meta.meta, call_role="return")
            )

        if hasattr(ret, "to_spec") and callable(getattr(ret, "to_spec")):
            base_spec = ret.to_spec()
            return replace(base_spec, meta=replace(base_spec.meta, call_role="return"))

        if ret is None or ret is inspect._empty:
            # We already know a value *is* returned (from body), but annotation is None/missing:
            # fallback to default leaf under 'result'
            leaf = SocketSpec(identifier=cls.TYPE_MAPPING["default"])
            return _wrap_leaf_as_ns(leaf)

        base_T, _meta = _unwrap_annotated(ret)
        if isinstance(base_T, SocketSpec):
            return replace(base_T, meta=replace(base_T.meta, call_role="return"))

        leaf = cls._spec_from_annotation(base_T)
        return _wrap_leaf_as_ns(leaf)

    @classmethod
    def infer_specs_from_callable(
        cls,
        callable_obj,
        inputs: SocketSpec | None,
        outputs: SocketSpec | None,
    ) -> tuple[SocketSpec | None, SocketSpec | None]:
        in_spec = cls.build_inputs_from_signature(callable_obj, inputs)
        out_spec = cls.build_outputs_from_signature(callable_obj, outputs)
        return in_spec, out_spec


def merge_specs(ns: SocketSpec, additions: SocketSpec) -> SocketSpec:
    """
    Merge two namespace specs, giving precedence to the fields in `additions`.
    """
    if not ns.is_namespace() or not additions.is_namespace():
        raise TypeError("merge_specs expects two namespace SocketSpecs.")
    new_fields = dict(ns.fields or {})
    new_fields.update(additions.fields or {})
    return replace(ns, fields=new_fields)


def _function_returns_value(func) -> bool:
    """
    True iff the *top-level* function body contains `return <non-None>`.

    Conservative defaults:
    - If source is unavailable, or AST parse fails, or the function node can't be found,
      return True (assume it returns a value).
    """
    try:
        src = inspect.getsource(func)
    except (OSError, TypeError):
        # No source (e.g., builtins). Be conservative: assume it DOES return a value
        return True

    src = textwrap.dedent(src)
    try:
        tree = ast.parse(src)
    except SyntaxError:
        # Be conservative: assume it DOES return a value
        return True

    # Find the outer function by name
    target_fn = None
    for node in tree.body:
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == func.__name__
        ):
            target_fn = node
            break
    if target_fn is None:
        # Conservative: assume it DOES return a value
        return True

    class _TopLevelReturnVisitor(ast.NodeVisitor):
        def __init__(self):
            self.returns_value = False

        # Don’t descend into nested defs/classes
        def visit_FunctionDef(self, node):  # nested defs: skip
            pass

        def visit_AsyncFunctionDef(self, node):
            pass

        def visit_ClassDef(self, node):
            pass

        def visit_Return(self, node: ast.Return):
            # `return` (no value) or `return None` -> does NOT produce an output value
            if node.value is None:
                return
            if isinstance(node.value, ast.Constant) and node.value.value is None:
                return
            self.returns_value = True

    v = _TopLevelReturnVisitor()
    for stmt in target_fn.body:
        v.visit(stmt)
        if v.returns_value:
            return True
    return False


def _set_leaf_default(ns: SocketSpec, path: tuple[str, ...], value: Any) -> SocketSpec:
    head, *rest = path
    child = ns.fields[head]
    if rest:
        if not child.is_namespace():
            raise TypeError("Path passes through a leaf.")
        return replace(
            ns, fields={**ns.fields, head: _set_leaf_default(child, tuple(rest), value)}
        )
    if child.is_namespace():
        raise TypeError("Cannot set default on a namespace.")
    return replace(ns, fields={**ns.fields, head: replace(child, default=value)})


def set_default(spec: SocketSpec | SocketView, dotted: str, value: Any) -> SocketSpec:
    root = spec.to_spec() if hasattr(spec, "to_spec") else spec
    return _set_leaf_default(root, tuple(dotted.split(".")), value)


def unset_default(spec: SocketSpec | SocketView, dotted: str) -> SocketSpec:
    from dataclasses import MISSING

    root = spec.to_spec() if hasattr(spec, "to_spec") else spec
    return _set_leaf_default(root, tuple(dotted.split(".")), MISSING)


# Convenience: expose classmethods directly (bound to the base class)
socket = BaseSocketSpecAPI.socket
namespace = BaseSocketSpecAPI.namespace
dynamic = BaseSocketSpecAPI.dynamic
expose = BaseSocketSpecAPI.expose
validate_socket_data = BaseSocketSpecAPI.validate_socket_data
infer_specs_from_callable = BaseSpecInferAPI.infer_specs_from_callable
