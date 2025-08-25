# node_graph/utils/function.py
from __future__ import annotations

import inspect
from typing import Any, get_type_hints, get_origin, get_args
from dataclasses import replace, is_dataclass, fields as dc_fields

from node_graph.socket_spec import (
    SocketSpec,
    SocketSpecMeta,
)
from node_graph.socket_spec import (
    _unwrap_annotated,
    _map_identifier,
)  # internal helpers

# ---------- Build SocketSpec from a function ----------


def _safe_type_hints(func):
    try:
        return get_type_hints(func, include_extras=True)
    except TypeError:
        return get_type_hints(func)


def _apply_namespace_defaults(
    ns_spec: SocketSpec, dv: dict[str, Any], type_mapping: dict[str, str]
) -> SocketSpec:
    """Recursively apply dict defaults to a namespace SocketSpec."""
    if ns_spec.identifier != type_mapping["namespace"]:
        return ns_spec
    new_fields: dict[str, SocketSpec] = {}
    child_defaults: dict[str, Any] = dict(ns_spec.defaults or {})
    for k, child in (ns_spec.fields or {}).items():
        if k in dv:
            val = dv[k]
            if isinstance(val, dict) and child.identifier == type_mapping["namespace"]:
                child = _apply_namespace_defaults(child, val, type_mapping=type_mapping)
            else:
                child_defaults[k] = val
        new_fields[k] = child
    return replace(ns_spec, fields=new_fields, defaults=child_defaults)


def _spec_from_annotation(T: Any, type_mapping: dict[str, str]) -> SocketSpec:
    """Best-effort conversion of an annotation into a SocketSpec.
    Supports: SocketSpec, objects with .to_spec(), dataclasses, TypedDict, and leaf types.
    """
    # Handles SocketView / Registered handles that expose .to_spec()
    if hasattr(T, "to_spec") and callable(getattr(T, "to_spec")):
        return T.to_spec()

    base_T, meta = _unwrap_annotated(T)
    meta = meta or SocketSpecMeta()

    # Already a SocketSpec
    if isinstance(base_T, SocketSpec):
        return base_T

    # Unannotated parameter sentinel -> leaf (default/any), not a namespace
    if base_T is inspect._empty:
        return SocketSpec(
            identifier=_map_identifier(Any, type_mapping=type_mapping), meta=meta
        )

    # Dataclass → static namespace of fields
    if isinstance(base_T, type) and is_dataclass(base_T):
        fields_spec: dict[str, SocketSpec] = {}
        for f in dc_fields(base_T):
            fields_spec[f.name] = _spec_from_annotation(
                f.type, type_mapping=type_mapping
            )
        return SocketSpec(
            identifier=type_mapping["namespace"], fields=fields_spec, meta=meta
        )

    # TypedDict / class with __annotations__ (only if non-empty)
    ann = getattr(base_T, "__annotations__", None)
    if isinstance(ann, dict) and bool(ann):
        fields_spec: dict[str, SocketSpec] = {}
        for name, tp in ann.items():
            fields_spec[name] = _spec_from_annotation(tp, type_mapping=type_mapping)
        return SocketSpec(
            identifier=type_mapping["namespace"], fields=fields_spec, meta=meta
        )

    # Fallback leaf
    return SocketSpec(
        identifier=_map_identifier(base_T, type_mapping=type_mapping), meta=meta
    )


def _build_inputs_from_signature(
    func, explicit: SocketSpec | None, type_mapping: dict[str, str]
) -> SocketSpec | None:
    """
    Comprehensive inputs spec builder from a function signature:
      - POSITIONAL_ONLY → call_role="args"
      - POSITIONAL_OR_KEYWORD / KEYWORD_ONLY → call_role="kwargs"
      - *args annotation: Tuple[T, ...] or T → dynamic namespace of item T, call_role="var_args"
      - **kwargs annotation: Dict[str, T] / Mapping[str, T] / T → dynamic namespace of item T, call_role="var_kwargs"
      - Parameters annotated with SocketSpec / SocketView (.to_spec) are respected
      - Defaults: plain defaults on leaves; dict defaults recursively applied to namespaces
    """
    if explicit is not None:
        if not isinstance(explicit, SocketSpec):
            raise TypeError("inputs must be a SocketSpec (namespace/dynamic)")
        return explicit

    sig = inspect.signature(func)
    ann_map = _safe_type_hints(func)

    fields: dict[str, SocketSpec] = {}
    defaults: dict[str, Any] = {}

    for name, param in sig.parameters.items():
        T = ann_map.get(name, param.annotation)
        base_T, meta = _unwrap_annotated(T)
        meta = meta or SocketSpecMeta()

        # Determine call_role
        if param.kind is inspect.Parameter.POSITIONAL_ONLY:
            call_role = "args"
        elif param.kind is inspect.Parameter.VAR_POSITIONAL:
            call_role = "var_args"
        elif param.kind is inspect.Parameter.VAR_KEYWORD:
            call_role = "var_kwargs"
        else:
            call_role = "kwargs"
        if meta.call_role is None:
            meta = replace(meta, call_role=call_role)

        # Determine required
        if meta.required is None:
            is_required = not (
                param.default is not inspect._empty
                or param.kind
                in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
            )
            meta = replace(meta, required=is_required)

        # Build base spec from annotation
        spec = _spec_from_annotation(base_T, type_mapping=type_mapping)
        # Merge meta (author meta has priority over derived)
        merged = SocketSpecMeta(
            help=meta.help if meta.help is not None else spec.meta.help,
            required=meta.required if meta.required is not None else spec.meta.required,
            widget=meta.widget if meta.widget is not None else spec.meta.widget,
            call_role=meta.call_role
            if meta.call_role is not None
            else spec.meta.call_role,
        )
        spec = replace(spec, meta=merged)

        # Expand varargs/kwargs into dynamic namespaces of item type
        if param.kind is inspect.Parameter.VAR_POSITIONAL:
            # *args: if annotation was Tuple[T, ...] use T, else use base_T
            origin = get_origin(base_T)
            args = get_args(base_T) or []
            item_T = (
                args[0]
                if (origin in (tuple,) and len(args) == 2 and args[1] is Ellipsis)
                else base_T
            )
            item_spec = _spec_from_annotation(item_T, type_mapping=type_mapping)
            spec = SocketSpec(
                identifier=type_mapping["namespace"],
                dynamic=True,
                item=item_spec,
                meta=merged,
            )
        elif param.kind is inspect.Parameter.VAR_KEYWORD:
            # **kwargs: if annotation Dict[str, T]/Mapping[str,T] pick value T; else use base_T
            origin = get_origin(base_T)
            args = get_args(base_T) or []
            val_T = args[1] if (origin in (dict,) and len(args) >= 2) else base_T
            item_spec = _spec_from_annotation(val_T, type_mapping=type_mapping)
            spec = SocketSpec(
                identifier=type_mapping["namespace"],
                dynamic=True,
                item=item_spec,
                meta=merged,
            )

        # Apply defaults
        if param.default is not inspect._empty:
            if (
                isinstance(param.default, dict)
                and spec.identifier == type_mapping["namespace"]
            ):
                spec = _apply_namespace_defaults(
                    spec, param.default, type_mapping=type_mapping
                )
            else:
                defaults[name] = param.default

        fields[name] = spec

    if not fields:
        return None
    return SocketSpec(
        identifier=type_mapping["namespace"], fields=fields, defaults=defaults
    )


def _build_outputs_from_signature(
    func, explicit: SocketSpec | None, type_mapping: dict[str, str]
) -> SocketSpec | None:
    """
    Comprehensive outputs spec builder from a function return annotation:
      - Explicit SocketSpec returned
      - Return annotation with SocketSpec / SocketView (.to_spec)
      - Tuple[T1, T2, ...] → static namespace {item0: T1, item1: T2, ...}
      - Tuple[T, ...] → dynamic namespace of item T
      - Mapping[str, T] / Dict[str, T] → dynamic namespace of item T
      - Dataclass / TypedDict → static namespace from fields
      - Leaf types → single leaf (engine exposes as 'result')
    """
    if explicit is not None:
        if not isinstance(explicit, SocketSpec):
            raise TypeError("outputs must be a SocketSpec (namespace/dynamic/leaf)")
        return explicit

    ann_map = _safe_type_hints(func)
    ret = ann_map.get("return", None)
    if ret is None or ret is inspect._empty:
        return SocketSpec(identifier=type_mapping["default"])  # single leaf 'result'

    # Handle SocketView-like
    if hasattr(ret, "to_spec") and callable(getattr(ret, "to_spec")):
        base_spec = ret.to_spec()
        return replace(base_spec, meta=replace(base_spec.meta, call_role="return"))

    base_T, meta = _unwrap_annotated(ret)
    meta = meta or SocketSpecMeta()

    # Already a SocketSpec
    if isinstance(base_T, SocketSpec):
        return replace(base_T, meta=replace(base_T.meta, call_role="return"))

    # Dataclass / TypedDict / __annotations__
    ann = getattr(base_T, "__annotations__", None)
    if (isinstance(base_T, type) and is_dataclass(base_T)) or isinstance(ann, dict):
        spec = _spec_from_annotation(base_T)
        return replace(spec, meta=replace(spec.meta, call_role="return"))

    # Tuples & Mappings
    from typing import Tuple, Dict as TDict
    import collections.abc as cabc

    origin = get_origin(base_T)
    args = list(get_args(base_T) or [])

    if origin in (tuple, Tuple):
        if len(args) == 2 and args[1] is Ellipsis:
            item_T = args[0]
            item_spec = _spec_from_annotation(item_T)
            return SocketSpec(
                identifier=type_mapping["namespace"],
                dynamic=True,
                item=item_spec,
                meta=SocketSpecMeta(call_role="return"),
            )
        else:
            fields_map: dict[str, SocketSpec] = {}
            for i, Ti in enumerate(args):
                fields_map[f"item{i}"] = _spec_from_annotation(Ti)
            return SocketSpec(
                identifier=type_mapping["namespace"],
                fields=fields_map,
                meta=SocketSpecMeta(call_role="return"),
            )

    if origin in (dict, TDict, cabc.Mapping):
        val_T = args[1] if len(args) >= 2 else Any
        item_spec = _spec_from_annotation(val_T)
        return SocketSpec(
            identifier=type_mapping["namespace"],
            dynamic=True,
            item=item_spec,
            meta=SocketSpecMeta(call_role="return"),
        )

    # Fallback leaf
    return SocketSpec(
        identifier=_map_identifier(base_T, type_mapping=type_mapping),
        meta=SocketSpecMeta(call_role="return"),
    )


def prepare_function_inputs(func, *call_args, **call_kwargs):
    """Prepare the inputs for the function call.
    This function extracts the arguments from the function signature and
    assigns them to the inputs dictionary."""
    import inspect

    inputs = dict(call_kwargs or {})
    if func is not None:
        arguments = list(call_args)
        orginal_func = func._func if hasattr(func, "_func") else func
        for name, parameter in inspect.signature(orginal_func).parameters.items():
            if parameter.kind in [
                parameter.POSITIONAL_ONLY,
                parameter.POSITIONAL_OR_KEYWORD,
            ]:
                try:
                    inputs[name] = arguments.pop(0)
                except IndexError:
                    pass
            elif parameter.kind is parameter.VAR_POSITIONAL:
                # not supported
                raise ValueError("VAR_POSITIONAL is not supported.")
    return inputs


def infer_specs_from_callable(callable, inputs, outputs, type_mapping: dict[str, str]):
    in_spec = _build_inputs_from_signature(callable, inputs, type_mapping=type_mapping)
    out_spec = _build_outputs_from_signature(
        callable, outputs, type_mapping=type_mapping
    )
    return in_spec, out_spec
