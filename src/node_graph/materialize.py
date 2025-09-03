from __future__ import annotations
from typing import Optional, Dict, Any, Literal
from copy import deepcopy
from node_graph.socket_spec import SocketSpec
from node_graph.orm.mapping import type_mapping as default_type_mapping
from node_graph.socket import SocketMetadata


def _spec_shape_snapshot(
    spec: SocketSpec, type_mapping: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Build a minimal, UI-friendly snapshot of a SocketSpec so runtime sockets
    expose their structure via `socket._metadata.extras`.

    Shape:
      {
        "identifier": "...",
        # if namespace:
        "sockets": { name: <snapshot>, ... },
        "dynamic": true,
        "item": <snapshot>,           # present only if dynamic
        "defaults": {...},            # optional
      }
    """
    type_mapping = type_mapping or default_type_mapping
    d: Dict[str, Any] = {"identifier": spec.identifier}

    if spec.identifier == type_mapping["namespace"]:
        # fixed fields
        if spec.fields:
            d["sockets"] = {
                k: _spec_shape_snapshot(v, type_mapping=type_mapping)
                for k, v in spec.fields.items()
            }

        # dynamic behavior
        if spec.dynamic:
            d["dynamic"] = True
            if spec.item is not None:
                d["item"] = _spec_shape_snapshot(spec.item, type_mapping=type_mapping)
            else:
                # fallback to 'any' when item is missing
                d["item"] = {"identifier": type_mapping.get("any", "node_graph.any")}

        # carry defaults
        if spec.defaults:
            d["defaults"] = deepcopy(spec.defaults)

    return d


def runtime_meta_from_spec(
    spec: SocketSpec,
    *,
    role: Literal["input", "output"],
    arg_role: Optional[str] = None,
    is_builtin: bool = False,
    function_generated: bool = False,
    link_limit_for_dynamic: int = 1_000_000,
    extra_overrides: Optional[Dict[str, Any]] = None,
    type_mapping: Dict[str, Any] = None,
) -> SocketMetadata:
    """
    Convert an author-time SocketSpec to runtime SocketMetadata (engine-facing).
    Also emits a shape snapshot into `extras` so tests and UIs can introspect:
      - extras["identifier"]
      - extras["sockets"] for fixed namespace fields
      - extras["dynamic"] + extras["item"] for dynamic namespaces
      - extras["defaults"] (optional)
      - extras["widget"] when present on the spec
    """
    type_mapping = type_mapping or default_type_mapping
    md: Dict[str, Any] = {}

    # required
    if spec.meta.required is not None:
        md["required"] = bool(spec.meta.required)

    # namespace features
    if spec.identifier == type_mapping["namespace"]:
        md["dynamic"] = bool(spec.dynamic)
        md["sub_socket_default_link_limit"] = (
            link_limit_for_dynamic if spec.dynamic else 1
        )
        md["sub_socket_default_link_limit"] = spec.meta.sub_socket_default_link_limit

    # runtime-only flags
    md["builtin_socket"] = bool(is_builtin)
    md["function_socket"] = bool(function_generated)

    # roles
    chosen_role = (
        arg_role
        or getattr(spec.meta, "call_role", None)
        or ("kwargs" if role == "input" else "return")
    )
    md["socket_type"] = "INPUT" if role == "input" else "OUTPUT"
    md["arg_type"] = chosen_role

    extras: Dict[str, Any] = _spec_shape_snapshot(spec, type_mapping=type_mapping)

    if spec.meta.widget is not None:
        extras["widget"] = spec.meta.widget

    if extra_overrides:
        extras.update(extra_overrides)

    if extras:
        md["extras"] = extras

    return SocketMetadata.from_raw(md)
