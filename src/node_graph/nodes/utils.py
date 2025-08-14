from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Union, Tuple, get_type_hints
from typing import get_origin, get_args
import inspect

from node_graph import spec


def inspect_function(
    func: Callable[..., Any]
) -> Tuple[
    List[List[Union[str, Any]]],
    Dict[str, Dict[str, Union[Any, Optional[Any]]]],
    Optional[str],
    Optional[str],
]:
    """Inspect function parameters (positional, kwargs, *args, **kwargs)."""
    signature = inspect.signature(func)
    args: List[List[Union[str, Any]]] = []
    kwargs: Dict[str, Dict[str, Union[Any, Optional[Any]]]] = {}
    var_args: Optional[str] = None
    var_kwargs: Optional[str] = None

    for name, parameter in signature.parameters.items():
        if parameter.kind == inspect.Parameter.POSITIONAL_ONLY:
            args.append([name, parameter.annotation])
        elif parameter.kind in (
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        ):
            kwargs[name] = {"type": parameter.annotation}
            if parameter.default is not inspect.Parameter.empty:
                kwargs[name]["default"] = parameter.default
                kwargs[name]["has_default"] = True
            else:
                kwargs[name]["has_default"] = False
        elif parameter.kind == inspect.Parameter.VAR_POSITIONAL:
            var_args = name
        elif parameter.kind == inspect.Parameter.VAR_KEYWORD:
            var_kwargs = name

    return args, kwargs, var_args, var_kwargs


def _is_namespace_type(tp: Any) -> bool:
    return spec.is_namespace_type(tp)


def _unwrap_annotated(tp: Any):
    """If tp is typing.Annotated[T, meta...], return (T, metas:list), else (tp, [])."""
    origin = get_origin(tp)
    if origin is not None and str(origin) == "typing.Annotated":
        args = get_args(tp)
        if args:
            return args[0], list(args[1:])
    return tp, []


def _get_socketmeta(metas: List[Any]):
    """Return first SocketMeta found in metas, else None."""
    for m in metas:
        if isinstance(m, spec.SocketMeta):
            return m
    return None


def _map_identifier(tp: Any, type_mapping: Dict[type, str]) -> str:
    """Map a Python type to an identifier via type_mapping."""
    if tp in type_mapping:
        return type_mapping[tp]
    origin = get_origin(tp)
    if origin in (list, tuple, set):
        return type_mapping.get(list, type_mapping["default"])
    return type_mapping.get("default", "node_graph.any")


def _unwrap_spec_field_type(tp: Any) -> tuple[Any, Optional[spec.SocketMeta]]:
    """Unwrap Annotated inside spec.namespace/spec.dynamic field types."""
    base, metas = _unwrap_annotated(tp)
    return base, _get_socketmeta(metas)


def _build_namespace_from_spec_type(
    ns_type: type,
    *,
    type_mapping: Dict[type, str],
    arg_type: str,
    default_values: Optional[Dict[str, Any]] = None,
    mark_function_socket: bool = True,
) -> Dict[str, Any]:
    """Build a socket spec dict from a spec.namespace/spec.dynamic type."""
    ns: Dict[str, Any] = {
        "identifier": type_mapping["namespace"],
        "sockets": {},
        "metadata": {"arg_type": arg_type},
    }
    if mark_function_socket:
        ns["metadata"]["function_socket"] = True

    # dynamic flag + item identifier (helpful for validation/UI)
    if getattr(ns_type, "__ng_dynamic__", False):
        ns["metadata"]["dynamic"] = True
        item_tp = getattr(ns_type, "__ng_item_type__", None)
        if item_tp is not None:
            base_item_tp, _meta_unused = _unwrap_spec_field_type(item_tp)
            # Always expose a simple identifier (back-compat)
            ns["metadata"]["item_identifier"] = _map_identifier(
                base_item_tp, type_mapping
            )
            # If the item is itself a namespace, expose a full nested namespace schema
            if _is_namespace_type(base_item_tp):
                item_ns = _build_namespace_from_spec_type(
                    base_item_tp,
                    type_mapping=type_mapping,
                    arg_type=arg_type,
                    default_values=None,
                    # Do NOT mark as function socket to avoid confusing UI on “template” items
                    mark_function_socket=False,
                )
                # Keep this under metadata to avoid clashing with fixed fields in `sockets`
                ns["metadata"]["item"] = item_ns

    fields: Dict[str, Any] = getattr(ns_type, "__ng_fields__", {}) or {}
    defaults: Dict[str, Any] = getattr(ns_type, "__ng_defaults__", {}) or {}
    dv = default_values or {}

    for name, f_type in fields.items():
        base_type, fmeta = _unwrap_spec_field_type(f_type)

        # Nested namespace
        if _is_namespace_type(base_type):
            child_defaults = dv.get(name) if isinstance(dv, dict) else None
            child = _build_namespace_from_spec_type(
                base_type,
                type_mapping=type_mapping,
                arg_type=arg_type,
                default_values=child_defaults,
                mark_function_socket=mark_function_socket,
            )
            ns["sockets"][name] = child
            continue

        # Leaf socket
        identifier = _map_identifier(base_type, type_mapping)

        # precedence: parameter defaults (dict) > spec defaults
        has_param_default = isinstance(dv, dict) and name in dv
        has_spec_default = name in defaults
        required = not (has_param_default or has_spec_default)
        if fmeta is not None and fmeta.required is not None:
            required = bool(fmeta.required)

        s: Dict[str, Any] = {
            "identifier": identifier,
            "metadata": {
                "arg_type": arg_type,
                "required": required,
            },
            "property": {"identifier": identifier},
        }
        if mark_function_socket:
            s["metadata"]["function_socket"] = True
        if fmeta is not None and fmeta.help:
            s["metadata"]["help"] = fmeta.help

        if has_param_default:
            s["property"]["default"] = dv[name]
        elif has_spec_default:
            s["property"]["default"] = defaults[name]

        ns["sockets"][name] = s

    return ns


def generate_input_sockets(
    func: Callable[..., Any],
    inputs: Optional[type] = None,
    type_mapping: Optional[Dict[type, str]] = None,
) -> Dict[str, Any]:
    """
    Build the inputs container.

    Policy:
      - If `inputs` is provided, it MUST be a spec type (namespace/dynamic) and is used exclusively.
      - Otherwise, infer from the function signature/annotations (supports spec.socket metadata).
      - Dict-based inputs are not supported anymore.
    """
    if type_mapping is None:
        from node_graph.orm.mapping import type_mapping as _default_tm

        type_mapping = _default_tm

    # explicit spec provided -> authoritative; no mixing
    if inputs:
        if not _is_namespace_type(inputs):
            raise TypeError("`inputs` must be a spec.namespace/spec.dynamic type.")
        ns = _build_namespace_from_spec_type(
            inputs,
            type_mapping=type_mapping,
            arg_type="explicit",
            default_values=None,
            mark_function_socket=True,
        )
        node_inputs = {
            "name": "inputs",
            "identifier": "node_graph.namespace",
            "sockets": ns["sockets"],
            "metadata": {"dynamic": bool(getattr(inputs, "__ng_dynamic__", False))},
        }
        return node_inputs

    # inferred from function signature
    args, kwargs, var_args, var_kwargs = inspect_function(func)

    try:
        ann = get_type_hints(func, include_extras=True)
    except TypeError:
        ann = get_type_hints(func)

    sockets: Dict[str, Any] = {}

    # Positional
    for name, raw_type in args:
        annotated_type, metas = _unwrap_annotated(ann.get(name, raw_type))
        meta = _get_socketmeta(metas)

        if _is_namespace_type(annotated_type):
            ns = _build_namespace_from_spec_type(
                annotated_type,
                type_mapping=type_mapping,
                arg_type="args",
                default_values=None,
            )
            ns["metadata"]["required"] = (
                True if (meta is None or meta.required is None) else bool(meta.required)
            )
            sockets[name] = ns
        else:
            ident = _map_identifier(annotated_type, type_mapping)
            required = (
                True if (meta is None or meta.required is None) else bool(meta.required)
            )
            s = {
                "identifier": ident,
                "metadata": {
                    "arg_type": "args",
                    "required": required,
                    "function_socket": True,
                },
            }
            if meta is not None and meta.help:
                s["metadata"]["help"] = meta.help
            sockets[name] = s

    # Keyword / defaults
    for name, kw in kwargs.items():
        annotated_type, metas = _unwrap_annotated(ann.get(name, kw.get("type")))
        meta = _get_socketmeta(metas)
        has_default = kw.get("has_default", False)
        default_val = kw.get("default", None)

        if _is_namespace_type(annotated_type):
            default_values = (
                default_val if (has_default and isinstance(default_val, dict)) else None
            )
            ns = _build_namespace_from_spec_type(
                annotated_type,
                type_mapping=type_mapping,
                arg_type="kwargs",
                default_values=default_values,
            )
            if meta is not None and meta.required is not None:
                ns.setdefault("metadata", {})["required"] = bool(meta.required)
            else:
                ns.setdefault("metadata", {})["required"] = not has_default
            sockets[name] = ns
        else:
            ident = _map_identifier(annotated_type, type_mapping)
            required = not has_default
            if meta is not None and meta.required is not None:
                required = bool(meta.required)
            s = {
                "identifier": ident,
                "metadata": {
                    "arg_type": "kwargs",
                    "required": required,
                    "function_socket": True,
                },
                "property": {"identifier": ident},
            }
            if meta is not None and meta.help:
                s["metadata"]["help"] = meta.help
            if has_default:
                s["property"]["default"] = default_val
            sockets[name] = s

    # *args -> namespace
    if var_args is not None:
        sockets[var_args] = {
            "identifier": type_mapping["namespace"],
            "metadata": {"arg_type": "var_args", "function_socket": True},
            "link_limit": 1_000_000,
        }

    # **kwargs -> dynamic namespace
    is_dynamic = False
    if var_kwargs is not None:
        sockets[var_kwargs] = {
            "identifier": type_mapping["namespace"],
            "metadata": {
                "arg_type": "var_kwargs",
                "dynamic": True,
                "function_socket": True,
            },
            "link_limit": 1_000_000,
        }
        is_dynamic = True

    node_inputs = {
        "name": "inputs",
        "identifier": "node_graph.namespace",
        "sockets": sockets,
        "metadata": {"dynamic": is_dynamic},
    }
    return node_inputs


def _build_output_from_spec_type(
    tp: Any, *, type_mapping: Dict[type, str]
) -> Dict[str, Any]:
    """Build a socket (or namespace) spec from a spec type for return paths."""
    if _is_namespace_type(tp):
        return _build_namespace_from_spec_type(
            tp,
            type_mapping=type_mapping,
            arg_type="return",
            default_values=None,
            mark_function_socket=True,
        )
    # Leaf
    ident = _map_identifier(tp, type_mapping)
    return {"identifier": ident, "metadata": {"arg_type": "return"}}


def generate_output_sockets(
    func: Callable[..., Any],
    outputs: Optional[type] = None,
    type_mapping: Optional[Dict[type, str]] = None,
) -> Dict[str, Any]:
    """Build outputs strictly from spec.*; everything else is a single leaf 'result'."""
    if type_mapping is None:
        from node_graph.orm.mapping import type_mapping as _default_tm

        type_mapping = _default_tm

    try:
        ann = get_type_hints(func, include_extras=True)
    except TypeError:
        ann = get_type_hints(func)

    ret = ann.get("return", None)

    is_dynamic = False
    extra_output_meta: Dict[str, Any] = {}
    # Use user-defined outputs if any, otherwise build from function return type
    ret = outputs or ret
    sockets = {}
    if ret is None:
        sockets["result"] = {
            "identifier": type_mapping.get("default", "node_graph.any")
        }
    elif _is_namespace_type(ret):
        ns = _build_output_from_spec_type(ret, type_mapping=type_mapping)

        # If return is a *static* namespace, flatten its fixed fields to top-level sockets
        if not getattr(ret, "__ng_dynamic__", False):
            for name, sock in ns.get("sockets", {}).items():
                sockets[name] = sock
        else:
            # Dynamic namespace (possibly with fixed fields) lives under 'result'
            sockets = ns["sockets"]
            is_dynamic = True
            # carry item metadata (including nested item namespace) up to the outputs container
            md = ns.get("metadata", {}) or {}
            for k in ("item_identifier", "item"):
                if k in md:
                    extra_output_meta[k] = md[k]
    else:
        # Everything else is a single leaf
        sockets["result"] = _build_output_from_spec_type(ret, type_mapping=type_mapping)

    for s in sockets.values():
        s.setdefault("metadata", {})["function_socket"] = True

    node_outputs = {
        "name": "outputs",
        "identifier": type_mapping["namespace"],
        "metadata": {
            "dynamic": is_dynamic,
            **(extra_output_meta if is_dynamic else {}),
        },
        "sockets": sockets,
    }

    return node_outputs
