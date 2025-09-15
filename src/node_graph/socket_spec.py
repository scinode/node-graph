from __future__ import annotations
from dataclasses import dataclass, field, replace, MISSING
from typing import (
    Any,
    Dict,
    Optional,
    Union,
    Iterable,
    Tuple,
)
import inspect
from copy import deepcopy
from node_graph.orm.mapping import type_mapping as DEFAULT_TM
from .socket import NodeSocketNamespace
import ast
import textwrap
import types
import sys

if sys.version_info < (3, 10):
    # Python 3.9 -> need typing_extensions for include_extras
    from typing_extensions import Annotated, get_args, get_origin, get_type_hints
else:
    from typing import Annotated, get_args, get_origin, get_type_hints

# Cache UnionType if available (3.10+), else None
_UNION_TYPE = getattr(types, "UnionType", None)

__all__ = [
    "SocketSpecMeta",
    "SocketSpecSelect",
    "SocketSpec",
    "SocketView",
    "BaseSocketSpecAPI",
    "BaseSpecInferAPI",
    "socket",
    "namespace",
    "dynamic",
    "validate_socket_data",
    "infer_specs_from_callable",
    "set_default",
    "unset_default",
    "merge_specs",
    "add_spec_field",
]


WidgetConfig = Union[str, Dict[str, Any]]


def _is_union_origin(origin: Any) -> bool:
    """True if origin represents a Union across versions (typing.Union or X|Y)."""
    return (origin is Union) or (_UNION_TYPE is not None and origin is _UNION_TYPE)


def _is_annotated_type(tp: Any) -> bool:
    """True if tp is an Annotated[...] wrapper across versions."""
    if get_origin(tp) is Annotated:
        return True
    # 3.9 fallback: Annotated instances expose __metadata__/__args__
    return hasattr(tp, "__metadata__") and hasattr(tp, "__args__")


def _find_first_annotated(tp: Any) -> Optional[Any]:
    """
    Return the first Annotated[...] wrapper found in tp, searching inside Union/Optional.
    (recurse into other generics is not supported.)
    """
    if _is_annotated_type(tp):
        return tp
    origin = get_origin(tp)
    if _is_union_origin(origin):
        for arg in get_args(tp):
            found = _find_first_annotated(arg)
            if found is not None:
                return found
    return None


def _annotated_parts(annot: Any) -> tuple[Any, tuple[Any, ...]]:
    """Given an Annotated wrapper, return (base_type, metadata_tuple)."""
    args = get_args(annot)
    base = args[0] if args else annot
    meta = getattr(annot, "__metadata__", None)
    if meta is None:
        meta = tuple(args[1:]) if len(args) > 1 else ()
    return base, tuple(meta)


def _unwrap_annotated(tp: Any) -> tuple[Any, Optional["SocketSpecMeta"]]:
    """Return (base_type, SocketSpecMeta|None) for Annotated types (incl. inside Optional/Union)."""
    annot = _find_first_annotated(tp)
    if annot is None:
        return tp, None
    base, metas = _annotated_parts(annot)
    spec_meta = next((m for m in metas if isinstance(m, SocketSpecMeta)), None)
    return base, spec_meta


def _extract_spec_from_annotated(tp: Any) -> Optional["SocketSpec"]:
    """
    Return a SocketSpec from Annotated metadata (preferring SocketView.to_spec()).
    Works when Annotated is nested in Optional/Union.
    """
    annot = _find_first_annotated(tp)
    if annot is None:
        return None
    _, metas = _annotated_parts(annot)
    for m in metas:
        if isinstance(m, SocketView):
            return m.to_spec()
    for m in metas:
        if isinstance(m, SocketSpec):
            return m
    return None


@dataclass(frozen=True)
class SocketSpecMeta:
    help: Optional[str] = None
    # by default all sockets are required
    required: Optional[bool] = True
    # "args" | "kwargs" | "var_args" | "var_kwargs" | "return"
    call_role: Optional[str] = None
    sub_socket_default_link_limit: Optional[int] = 1
    is_metadata: Optional[bool] = False
    widget: Optional[WidgetConfig] = None


def _merge_meta(base: "SocketSpecMeta", over: "SocketSpecMeta") -> "SocketSpecMeta":
    """Overlay non-None fields from `over` onto `base`."""
    return SocketSpecMeta(
        help=over.help if over.help is not None else base.help,
        required=over.required if over.required is not None else base.required,
        call_role=over.call_role if over.call_role is not None else base.call_role,
        sub_socket_default_link_limit=(
            over.sub_socket_default_link_limit
            if over.sub_socket_default_link_limit is not None
            else base.sub_socket_default_link_limit
        ),
        is_metadata=over.is_metadata
        if over.is_metadata is not None
        else base.is_metadata,
        widget=over.widget if over.widget is not None else base.widget,
    )


@dataclass(frozen=True)
class SocketSpecSelect:
    """
    Selection/transform directives used *only* inside Annotated metadata.

    - include/exclude support dotted paths ("a.b.c"). When `include` is provided,
      unspecified fields are dropped; `exclude` removes the specified fields.
    - include_prefix/exclude_prefix match *top-level* field names only.
    - rename maps top-level child names.
    - prefix prepends a string to all top-level child names.
    """

    include: Optional[Union[str, Iterable[str]]] = None
    exclude: Optional[Union[str, Iterable[str]]] = None
    include_prefix: Optional[Union[str, Iterable[str]]] = None
    exclude_prefix: Optional[Union[str, Iterable[str]]] = None
    rename: Optional[Dict[str, str]] = None
    prefix: Optional[str] = None

    def __post_init__(self):
        object.__setattr__(self, "include", _normalize_names(self.include))
        object.__setattr__(self, "exclude", _normalize_names(self.exclude))
        object.__setattr__(
            self, "include_prefix", _normalize_names(self.include_prefix)
        )
        object.__setattr__(
            self, "exclude_prefix", _normalize_names(self.exclude_prefix)
        )


def _normalize_names(
    x: Optional[Union[str, Iterable[str]]]
) -> Optional[Tuple[str, ...]]:
    if x is None:
        return None
    if isinstance(x, str):
        return (x,)
    return tuple(x)


def _paths_to_tree(names: Iterable[str]) -> Dict[str, Optional[dict]]:
    """
    Convert ["a", "b.c", "b.d.e"] -> {"a": None, "b": {"c": None, "d": {"e": None}}}
    None means "take/remove this entire field".
    If a parent key is already marked None (whole subtree), deeper paths under it are ignored.
    """
    root: Dict[str, Optional[dict]] = {}
    for raw in names or []:
        parts = [p for p in str(raw).split(".") if p]
        if not parts:
            continue
        node: Dict[str, Optional[dict]] = root
        for i, seg in enumerate(parts):
            last = i == len(parts) - 1
            if last:
                # Mark whole field at this level
                node[seg] = None
            else:
                if seg not in node:
                    node[seg] = {}
                else:
                    # If already selecting whole subtree, deeper spec is irrelevant
                    if node[seg] is None:
                        # parent marked as whole selection/removal: stop descending
                        break
                    # if it exists but isn't a dict (shouldn't happen), coerce to dict
                    if not isinstance(node[seg], dict):
                        node[seg] = {}
                # descend
                node = node[seg]
    return root


def _spec_include(spec: "SocketSpec", tree: Dict[str, Optional[dict]]) -> "SocketSpec":
    if not spec.is_namespace():
        return spec
    keep: Dict[str, SocketSpec] = {}
    for k, subtree in tree.items():
        if k not in spec.fields:
            continue
        child = spec.fields[k]
        keep[k] = (
            child
            if subtree is None
            else (_spec_include(child, subtree) if child.is_namespace() else child)
        )
    return replace(spec, fields=keep)


def _spec_exclude(spec: "SocketSpec", tree: Dict[str, Optional[dict]]) -> "SocketSpec":
    if not spec.is_namespace():
        return spec
    new_fields = dict(spec.fields)
    for k, subtree in tree.items():
        if k not in new_fields:
            continue
        if subtree is None:
            new_fields.pop(k, None)
        else:
            child = new_fields[k]
            if child.is_namespace():
                new_fields[k] = _spec_exclude(child, subtree)
    return replace(spec, fields=new_fields)


def _spec_rename(spec: "SocketSpec", mapping: Dict[str, str]) -> "SocketSpec":
    if not spec.is_namespace():
        raise TypeError("rename requires a namespace SocketSpec")
    out: Dict[str, SocketSpec] = {}
    for old, child in spec.fields.items():
        new = mapping.get(old, old)
        if new in out:
            raise ValueError(f"rename collision: '{new}'")
        out[new] = child
    return replace(spec, fields=out)


def _spec_prefix(spec: "SocketSpec", pfx: str) -> "SocketSpec":
    if not spec.is_namespace():
        raise TypeError("prefix requires a namespace SocketSpec")
    return replace(spec, fields={f"{pfx}{k}": v for k, v in spec.fields.items()})


def _expand_prefix_names(
    spec: "SocketSpec", pfxs: Optional[Iterable[str]]
) -> list[str]:
    if not pfxs or not spec.is_namespace():
        return []
    pfxs = list(pfxs)
    return [k for k in spec.fields.keys() if any(k.startswith(p) for p in pfxs)]


def _apply_select_from_annotation(annot_like: Any, spec: "SocketSpec") -> "SocketSpec":
    """Collect & apply all SocketSpecSelect objects found in Annotated metadata."""
    annot = _find_first_annotated(annot_like)
    if annot is None:
        return spec
    _, metas = _annotated_parts(annot)

    s = spec
    for m in metas:
        if not isinstance(m, SocketSpecSelect):
            continue
        inc = list(m.include or [])
        exc = list(m.exclude or [])
        inc += _expand_prefix_names(s, m.include_prefix)
        exc += _expand_prefix_names(s, m.exclude_prefix)
        if inc:
            s = _spec_include(s, _paths_to_tree(inc))
        if exc:
            s = _spec_exclude(s, _paths_to_tree(exc))
        if m.rename:
            s = _spec_rename(s, m.rename)
        if m.prefix:
            s = _spec_prefix(s, m.prefix)
    return s


def _merge_all_meta_from_annotation(
    annot_like: Any, base: "SocketSpecMeta"
) -> "SocketSpecMeta":
    """Overlay every SocketSpecMeta present in Annotated metadata (order-respecting)."""
    annot = _find_first_annotated(annot_like)
    if annot is None:
        return base
    _, metas = _annotated_parts(annot)
    out = base
    for m in metas:
        if isinstance(m, SocketSpecMeta):
            out = _merge_meta(out, m)
    return out


@dataclass(frozen=True)
class SocketSpec:
    """
    Immutable socket schema tree (leaf or namespace).

    - identifier: leaf type identifier or "node_graph.namespace"
    - dynamic: namespace accepts arbitrary keys (item gives per-key schema)
    - item: schema for each dynamic key (leaf or namespace)
    - fields: fixed fields for namespace (name -> schema)
    - default: leaf-only default value
    - meta: optional meta (help/required/widget/is_metadata/call_role/sub_socket_default_link_limit)
    """

    identifier: str
    dynamic: bool = False
    item: Optional["SocketSpec"] = None
    default: Any = field(default_factory=lambda: MISSING)
    fields: Dict[str, "SocketSpec"] = field(default_factory=dict)
    meta: SocketSpecMeta = field(default_factory=SocketSpecMeta)

    # structural predicates
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
        # default only for leaves and only if not MISSING
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
                "is_metadata",  # ensure serialized
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
                    "is_metadata",
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


def _is_namespace(spec: SocketSpec) -> bool:
    return spec.is_namespace()


def _ensure_namespace(spec: SocketSpec) -> None:
    if not _is_namespace(spec):
        raise TypeError("Operation requires a namespace SocketSpec")


class SocketView:
    """A lightweight, pure view over a SocketSpec for attribute traversal. No mutators."""

    __slots__ = ("_spec",)

    def __init__(self, spec: SocketSpec) -> None:
        object.__setattr__(self, "_spec", spec)

    def to_spec(self) -> SocketSpec:
        return object.__getattribute__(self, "_spec")

    def __getattr__(self, name: str) -> "SocketView":
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

    TYPE_MAPPING: Dict[Union[str, Any], str] = DEFAULT_TM

    # convenience re-exports
    SocketSpec = SocketSpec
    SocketSpecMeta = SocketSpecMeta
    SocketSpecSelect = SocketSpecSelect
    SocketView = SocketView
    SocketNamespace = NodeSocketNamespace

    @classmethod
    def socket(cls, T: Any, **meta) -> Any:
        """Wrap a type with optional metadata (help/required/widget/etc.)."""
        return Annotated[T, SocketSpecMeta(**meta)]

    @classmethod
    def namespace(cls, _name: Optional[str] = None, /, **fields) -> SocketSpec:
        tm = cls.TYPE_MAPPING
        spec = SocketSpec(identifier=tm["namespace"])
        new_fields: Dict[str, SocketSpec] = {}

        for name, val in fields.items():
            has_default = isinstance(val, tuple) and len(val) == 2
            T, default_val = val if has_default else (val, MISSING)

            annotated_spec = _extract_spec_from_annotated(T)
            if annotated_spec is not None:
                child = annotated_spec
            else:
                base_T, _ = _unwrap_annotated(T)
                if isinstance(base_T, SocketSpec):
                    child = base_T
                elif isinstance(base_T, SocketView):
                    child = base_T.to_spec()
                else:
                    child = SocketSpec(
                        identifier=cls._map_identifier(base_T), meta=SocketSpecMeta()
                    )

            # Overlay *all* SocketSpecMeta present in Annotated metadata
            child = replace(child, meta=_merge_all_meta_from_annotation(T, child.meta))
            # Apply selection/transform directives
            child = _apply_select_from_annotation(T, child)

            # Scalar default only on leaves
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
        T, _ = _unwrap_annotated(item_type)
        item_spec = (
            T
            if isinstance(T, SocketSpec)
            else SocketSpec(identifier=cls._map_identifier(T), meta=SocketSpecMeta())
        )
        return replace(base, item=item_spec)

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
        """Validate socket data and convert it to a dictionary."""
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
    """Strict inference: no structural guessing into namespaces."""

    TYPE_MAPPING: Dict[Union[str, Any], str] = DEFAULT_TM
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
            # python 3.9 using typing_extensions.get_type_hints
            return get_type_hints(func)

    @staticmethod
    def _is_namespace(spec: SocketSpec) -> bool:
        return bool(spec.dynamic or spec.fields)

    @classmethod
    def _apply_structured_defaults_to_leaves(
        cls, ns_spec: SocketSpec, dv: dict[str, Any]
    ) -> SocketSpec:
        """Recursively apply dict defaults by setting defaults on leaf specs only."""
        if not cls._is_namespace(ns_spec):
            return ns_spec
        new_fields: dict[str, SocketSpec] = {}
        for k, child in (ns_spec.fields or {}).items():
            if k not in dv:
                new_fields[k] = child
                continue
            val = dv[k]
            if isinstance(val, dict) and cls._is_namespace(child):
                new_fields[k] = cls._apply_structured_defaults_to_leaves(child, val)
            else:
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

        base_T, _meta_ignored = _unwrap_annotated(T)
        # Already a SocketSpec
        if isinstance(base_T, SocketSpec):
            return base_T

        return SocketSpec(identifier=cls._map_identifier(base_T), meta=SocketSpecMeta())

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
            base_T, _ = _unwrap_annotated(T)

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

            # Determine required
            is_required = not (
                param.default is not inspect._empty
                or param.kind
                in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
            )

            # Prefer spec from Annotated metadata if present
            annotated_spec = _extract_spec_from_annotated(T)
            if annotated_spec is not None:
                spec = annotated_spec
            else:
                spec = cls._spec_from_annotation(base_T)

            # Merge *all* SocketSpecMeta from annotation, overlaying required/call_role defaults
            merged_meta = _merge_all_meta_from_annotation(
                T,
                SocketSpecMeta(
                    required=is_required,
                    call_role=call_role,
                ),
            )
            spec = replace(spec, meta=_merge_meta(spec.meta, merged_meta))

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

            # Apply selection/transform directives from Annotated
            spec = _apply_select_from_annotation(T, spec)

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
        """Always return a NAMESPACE spec, with selection/meta applied.
        - If the function body never does `return <value>`, return an EMPTY namespace,
        regardless of annotations.
        - Otherwise, honor explicit, Annotated, or wrap leaf under DEFAULT_OUTPUT_KEY.
        """

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
                return replace(
                    explicit, meta=replace(explicit.meta, call_role="return")
                )
            return _wrap_leaf_as_ns(explicit)

        # If function body never returns a value -> EMPTY namespace
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

        # Explicit spec from metadata
        spec_from_meta = _extract_spec_from_annotated(ret)
        if spec_from_meta is not None:
            spec_from_meta = _apply_select_from_annotation(ret, spec_from_meta)
            spec_from_meta = replace(
                spec_from_meta,
                meta=_merge_all_meta_from_annotation(ret, spec_from_meta.meta),
            )
            return replace(
                spec_from_meta, meta=replace(spec_from_meta.meta, call_role="return")
            )

        # to_spec() on annotation object
        if hasattr(ret, "to_spec") and callable(getattr(ret, "to_spec")):
            base_spec = ret.to_spec()
            base_spec = _apply_select_from_annotation(ret, base_spec)
            base_spec = replace(
                base_spec, meta=_merge_all_meta_from_annotation(ret, base_spec.meta)
            )
            return replace(base_spec, meta=replace(base_spec.meta, call_role="return"))

        # Fallback leaf under 'result'
        if ret is None or ret is inspect._empty:
            leaf = SocketSpec(identifier=cls.TYPE_MAPPING["default"])
            return _wrap_leaf_as_ns(leaf)

        base_T, _ = _unwrap_annotated(ret)
        if isinstance(base_T, SocketSpec):
            base_T = _apply_select_from_annotation(ret, base_T)
            base_T = replace(
                base_T, meta=_merge_all_meta_from_annotation(ret, base_T.meta)
            )
            return replace(base_T, meta=replace(base_T.meta, call_role="return"))

        leaf = cls._spec_from_annotation(base_T)
        leaf = _apply_select_from_annotation(ret, leaf)
        leaf = replace(leaf, meta=_merge_all_meta_from_annotation(ret, leaf.meta))
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


def add_spec_field(ns: SocketSpec, name: str, spec: SocketSpec) -> SocketSpec:
    """
    Add a new field to a namespace spec. Raises if the field already exists.
    """
    if not ns.is_namespace():
        raise TypeError("add_spec_field expects a namespace SocketSpec.")
    if name in ns.fields:
        raise ValueError(f"Field '{name}' already exists in the namespace.")
    new_fields = dict(ns.fields or {})
    new_fields[name] = spec
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

        def visit_FunctionDef(self, node):  # skip nested
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
    root = spec.to_spec() if hasattr(spec, "to_spec") else spec
    return _set_leaf_default(root, tuple(dotted.split(".")), MISSING)


# Convenience: expose classmethods directly (bound to the base class)
socket = BaseSocketSpecAPI.socket
namespace = BaseSocketSpecAPI.namespace
dynamic = BaseSocketSpecAPI.dynamic
validate_socket_data = BaseSocketSpecAPI.validate_socket_data
infer_specs_from_callable = BaseSpecInferAPI.infer_specs_from_callable
