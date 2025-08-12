from __future__ import annotations

from typing import Any, Annotated
import itertools

__all__ = ["namespace", "dynamic", "socket", "SocketMeta", "is_namespace_type"]


class SocketMeta:
    """Optional input metadata (help/required/widget)."""

    def __init__(
        self,
        *,
        help: str | None = None,
        required: bool | None = None,
        widget: str | None = None,
    ):
        self.help = help
        self.required = required
        self.widget = widget


def socket(T: Any, **meta) -> Any:
    """Wrap a type with optional input metadata."""
    return Annotated[T, SocketMeta(**meta)]


_counter = itertools.count(1)


def _make_namespace_type(
    name: str,
    *,
    fields: dict[str, Any],
    defaults: dict[str, Any],
    dynamic: bool,
    item_type: Any | None,
):
    """Create a lightweight 'type' that carries namespace spec metadata."""
    attrs = {
        "__ng_namespace__": True,  # marker: this is a namespace spec
        "__ng_dynamic__": dynamic,  # True if namespace accepts arbitrary key->item_type
        "__ng_item_type__": item_type,  # the item type for dynamic keys
        "__ng_fields__": fields,  # fixed fields: name -> type (or nested spec)
        "__ng_defaults__": defaults,  # field defaults: name -> value
        "__module__": __name__,
    }
    return type(name, (object,), attrs)


def namespace(_name: str | None = None, /, **fields: Any):
    """
    Define a *static* SocketNamespace.
    Usage:
        Out = namespace(sum=int, difference=int)
        With defaults: namespace(a=(int, 1), b=int)
    """
    name = _name or f"NS_{next(_counter)}"
    processed, defaults = {}, {}
    for k, v in fields.items():
        if isinstance(v, tuple) and len(v) == 2:
            typ, default = v
            processed[k] = typ
            defaults[k] = default
        else:
            processed[k] = v
    return _make_namespace_type(
        name, fields=processed, defaults=defaults, dynamic=False, item_type=None
    )


def dynamic(item_type: Any, /, **fixed: Any):
    """
    Define a *dynamic* SocketNamespace (keys are str -> item_type).
    You can also add fixed named sockets alongside the dynamic catch-all:
        dynamic(int)                       # pure dynamic
        dynamic(int, total=int)            # dynamic + fixed field(s)
        dynamic(namespace(...))            # dynamic of a namespace
    Defaults: dynamic(int, a=(int, 1))
    """
    name = f"DYN_{next(_counter)}"
    processed, defaults = {}, {}
    for k, v in fixed.items():
        if isinstance(v, tuple) and len(v) == 2:
            typ, default = v
            processed[k] = typ
            defaults[k] = default
        else:
            processed[k] = v
    return _make_namespace_type(
        name, fields=processed, defaults=defaults, dynamic=True, item_type=item_type
    )


def is_namespace_type(tp: Any) -> bool:
    """Return True if 'tp' is a type produced by spec.namespace/spec.dynamic."""
    return isinstance(tp, type) and getattr(tp, "__ng_namespace__", False) is True
