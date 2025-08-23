# node_graph/socket_spec.py
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Dict, Optional, Union, get_origin, get_args, Annotated, Iterable
from copy import deepcopy

# Reuse your mapping: python type -> identifier (e.g. "node_graph.int", "node_graph.namespace", ...)
from node_graph.orm.mapping import type_mapping
from node_graph.socket import NodeSocket, NodeSocketNamespace
from node_graph.orm.mapping import type_mapping as DEFAULT_TM

WidgetConfig = Union[str, Dict[str, Any]]  # Simple, flexible UI hint

# ------------ Core schema (authoring-time) ------------


@dataclass(frozen=True)
class SocketSpecMeta:
    help: Optional[str] = None
    required: Optional[bool] = None
    # call role informs how this socket participates in function calling
    # one of: "args" | "kwargs" | "var_args" | "var_kwargs" | "return"
    call_role: Optional[str] = None
    widget: Optional[WidgetConfig] = None  # UI hint only; engines may ignore


@dataclass(frozen=True)
class SocketSpec:
    """
    Immutable socket schema tree (leaf or namespace).
    - identifier: leaf type identifier or "node_graph.namespace"
    - dynamic: namespace accepts arbitrary keys (item gives per-key schema)
    - item: schema for each dynamic key (leaf or namespace)
    - fields: fixed fields for namespace (name -> schema)
    - defaults: default values for fixed fields (for leaf sockets only)
    - meta: optional meta (help/required/widget)
    """

    identifier: str
    dynamic: bool = False
    item: Optional["SocketSpec"] = None
    fields: Dict[str, "SocketSpec"] = field(default_factory=dict)
    defaults: Dict[str, Any] = field(default_factory=dict)
    meta: SocketSpecMeta = field(default_factory=SocketSpecMeta)

    # ---- transforms & (de)serialization ----

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "identifier": self.identifier,
            "dynamic": self.dynamic,
        }
        if self.item is not None:
            d["item"] = self.item.to_dict()
        if self.fields:
            d["fields"] = {k: v.to_dict() for k, v in self.fields.items()}
        if self.defaults:
            d["defaults"] = deepcopy(self.defaults)
        if any(
            getattr(self.meta, k) is not None for k in ("help", "required", "widget")
        ):
            d["meta"] = {
                k: getattr(self.meta, k)
                for k in ("help", "required", "widget")
                if getattr(self.meta, k) is not None
            }
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SocketSpec":
        meta = SocketSpecMeta(**d.get("meta", {}))
        item = cls.from_dict(d["item"]) if "item" in d else None
        fields = {k: cls.from_dict(v) for k, v in d.get("fields", {}).items()}
        return cls(
            identifier=d["identifier"],
            dynamic=bool(d.get("dynamic", False)),
            item=item,
            fields=fields,
            defaults=deepcopy(d.get("defaults", {})),
            meta=meta,
        )

    # ---- fluent namespace transforms (expose) ----

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
        new_defaults = {mapping.get(k, k): v for k, v in self.defaults.items()}
        return replace(self, fields=new_fields, defaults=new_defaults)

    def prefix(self, pfx: str) -> "SocketSpec":
        _ensure_namespace(self)
        new_fields = {f"{pfx}{k}": v for k, v in self.fields.items()}
        new_defaults = {f"{pfx}{k}": v for k, v in self.defaults.items()}
        return replace(self, fields=new_fields, defaults=new_defaults)

    @classmethod
    def from_namespace(
        cls,
        live: NodeSocketNamespace,
        *,
        role: str = "input",
        type_mapping: Optional[dict] = None,
    ) -> "SocketSpec":
        """Snapshot the *current* shape of a live NodeSocketNamespace into a SocketSpec.
        Recurses nested namespaces, maps leaf sockets with the configured type_mapping.
        **Preserves** whether the namespace is dynamic, and sets an `item` spec (defaults to `any`).
        """
        tm = type_mapping or DEFAULT_TM

        def _leaf_spec(sock: NodeSocket) -> "SocketSpec":
            ident = getattr(sock, "_identifier", None) or tm.get(
                "default", "node_graph.any"
            )
            key = ident.split(".")[-1]
            mapped = tm.get(key, ident)
            return SocketSpec(identifier=mapped)

        def _ns_spec(ns: NodeSocketNamespace) -> "SocketSpec":
            # children first
            fields: dict[str, SocketSpec] = {}
            for name, child in ns._sockets.items():
                if isinstance(child, NodeSocketNamespace):
                    fields[name] = _ns_spec(child)
                else:
                    fields[name] = _leaf_spec(child)
            # base namespace
            spec = SocketSpec(identifier=tm["namespace"], fields=fields)
            # carry dynamic flag & item rule if dynamic
            if ns._metadata.dynamic:
                any_item = SocketSpec(identifier=tm.get("any", "node_graph.any"))
                spec = replace(spec, dynamic=True, item=any_item)
            return spec

        return _ns_spec(live)


# ------------ Authoring sugar (single concept: socket) ------------


def socket(T: Any, **meta) -> Any:
    """Typing sugar: socket(T, help=..., required=..., widget=...) -> Annotated[T, SocketSpecMeta]."""
    return Annotated[T, SocketSpecMeta(**meta)]


def namespace(
    _name: str | None = None, /, *, type_mapping: dict = DEFAULT_TM, **fields
) -> SocketSpec:
    """Static namespace: fields=name -> type or (type, default)."""
    spec = SocketSpec(identifier=type_mapping["namespace"])
    new_fields: Dict[str, SocketSpec] = {}
    defaults: Dict[str, Any] = {}
    for name, val in fields.items():
        has_default = isinstance(val, tuple) and len(val) == 2
        T, default = val if has_default else (val, None)
        base_T, meta = _unwrap_annotated(T)
        s_meta = meta or SocketSpecMeta()
        child = (
            base_T
            if isinstance(base_T, SocketSpec)
            else SocketSpec(
                identifier=_map_identifier(base_T, type_mapping=type_mapping),
                meta=s_meta,
            )
        )
        new_fields[name] = child
        if has_default:
            defaults[name] = default
    return replace(spec, fields=new_fields, defaults=defaults)


def dynamic(
    item_type: Any, /, *, type_mapping: dict = DEFAULT_TM, **fixed
) -> SocketSpec:
    """Dynamic namespace with optional fixed fields."""
    base = namespace(type_mapping=type_mapping, **fixed)
    base = replace(base, dynamic=True)
    T, meta = _unwrap_annotated(item_type)
    s_meta = meta or SocketSpecMeta()
    item_spec = (
        T
        if isinstance(T, SocketSpec)
        else SocketSpec(
            identifier=_map_identifier(T, type_mapping=type_mapping), meta=s_meta
        )
    )
    return replace(base, item=item_spec)


# ------------ Expose helper (works on SocketSpec or a view) ------------


def expose(
    spec_or_view: SocketSpec | "SocketView",
    *,
    include: Iterable[str] | None = None,
    exclude: Iterable[str] | None = None,
    rename: Dict[str, str] | None = None,
    prefix: str | None = None,
) -> SocketSpec:
    spec = (
        spec_or_view.to_spec() if isinstance(spec_or_view, SocketView) else spec_or_view
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


# ------------ Utility view for fluent include/exclude on registered nodes ------------


class SocketView:
    def __init__(self, spec: SocketSpec) -> None:
        self._spec = spec

    def include(self, *names: str) -> "SocketView":
        return SocketView(self._spec.include(*names))

    def exclude(self, *names: str) -> "SocketView":
        return SocketView(self._spec.exclude(*names))

    def only(self, *names: str) -> "SocketView":
        return SocketView(self._spec.only(*names))

    def rename(self, mapping: Dict[str, str]) -> "SocketView":
        return SocketView(self._spec.rename(mapping))

    def prefix(self, pfx: str) -> "SocketView":
        return SocketView(self._spec.prefix(pfx))

    def to_spec(self) -> SocketSpec:
        return self._spec

    def __getattr__(self, name: str) -> "SocketView":
        spec = self._spec
        if name == "item":
            if (
                spec.identifier == type_mapping["namespace"]
                and spec.dynamic
                and spec.item is not None
            ):
                return SocketView(spec.item)
            raise AttributeError("'.item' only valid on dynamic namespace specs")
        if spec.identifier == type_mapping["namespace"] and name in (spec.fields or {}):
            return SocketView(spec.fields[name])
        raise AttributeError(f"'{name}' not found in namespace spec")

    def __getitem__(self, name: str) -> "SocketView":
        # symmetric to __getattr__ for ergonomic ['field'] selection
        return self.__getattr__(name)


# ------------ helpers ------------


def _map_identifier(tp: Any, type_mapping: dict) -> str:
    if tp in type_mapping:
        return type_mapping[tp]
    origin = get_origin(tp)
    if origin in (list, tuple, set):
        return type_mapping.get(list, type_mapping["default"])
    return type_mapping.get("default", "node_graph.any")


def _unwrap_annotated(tp: Any) -> tuple[Any, Optional[SocketSpecMeta]]:
    origin = get_origin(tp)
    if origin is Annotated:
        args = list(get_args(tp))
        base = args[0]
        m = next((a for a in args[1:] if isinstance(a, SocketSpecMeta)), None)
        return base, m
    return tp, None


def _ensure_namespace(spec: SocketSpec, type_mapping: dict = None) -> None:
    # if spec.identifier != type_mapping["namespace"]:
    # this is not strictly correct.
    print("identifier: ", spec.identifier)
    if "namespace" not in spec.identifier:
        raise TypeError("Expose/rename/prefix require a namespace SocketSpec")
