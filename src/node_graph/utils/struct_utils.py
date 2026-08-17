from __future__ import annotations

from dataclasses import asdict, is_dataclass
from enum import Enum
from typing import Any, Dict
import importlib

from pydantic import BaseModel


def is_enum_type(tp: Any) -> bool:
    """Return True for Enum subclasses (including ``str``- and ``int``-Enum)."""
    return isinstance(tp, type) and issubclass(tp, Enum)


def is_structured_instance(value: Any) -> bool:
    """Return True for dataclass or Pydantic model instances."""
    return (is_dataclass(value) and not isinstance(value, type)) or isinstance(
        value, BaseModel
    )


def structured_to_dict(value: Any) -> Any:
    """Convert structured instances to plain dicts for namespace wiring."""
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, BaseModel):
        if contains_tagged_value(value):
            return {
                name: structured_to_dict(getattr(value, name))
                for name in value.model_fields
            }
        return value.model_dump(exclude_none=False)
    return value


def structured_type_info(tp: Any) -> Dict[str, str] | None:
    """Return a serializable descriptor for structured types (incl. ``Enum``)."""
    if is_dataclass(tp):
        return {"kind": "dataclass", "path": structured_type_path(tp)}
    if isinstance(tp, type) and issubclass(tp, BaseModel):
        return {"kind": "pydantic", "path": structured_type_path(tp)}
    if is_enum_type(tp):
        return {"kind": "enum", "path": structured_type_path(tp)}
    return None


def structured_type_path(tp: Any) -> str:
    return f"{tp.__module__}.{tp.__qualname__}"


def import_structured_type(path: str) -> Any:
    module_path, _, attr_path = path.rpartition(".")
    module = importlib.import_module(module_path)
    current = module
    for part in attr_path.split("."):
        current = getattr(current, part)
    return current


#: Literal arguments a spec can carry through a to_dict/from_dict round trip.
JSON_SAFE_LITERALS = (str, bool, int, type(None))


def untagged(value: Any) -> Any:
    """Return the value a ``TaggedValue`` wraps, else ``value``.

    Canonicalization builds a fresh object, so the proxy has to come off first:
    ``isinstance`` reports the wrapped type and would otherwise pass a proxy on
    where callers expect a plain value.
    """
    from node_graph.socket import TaggedValue

    return value.__wrapped__ if isinstance(value, TaggedValue) else value


def literal_value(value: Any) -> Any:
    """Return the bare value an ``Enum`` member stands for, else ``value``."""
    return value.value if isinstance(value, Enum) else value


def value_is_allowed(value: Any, allowed: Any) -> bool:
    """Return True when ``value`` is one of ``allowed``.

    Follows typing's rule that ``True`` is not ``1``: a value matches only a
    candidate of its own type.
    """
    return any(type(item) is type(value) and item == value for item in allowed)


def format_allowed_values(allowed: Any) -> str:
    """Render allowed values as ``'a', 'b' or 'c'``."""
    rendered = [repr(item) for item in allowed]
    if not rendered:
        return "<nothing>"
    if len(rendered) == 1:
        return rendered[0]
    return f"{', '.join(rendered[:-1])} or {rendered[-1]}"


def _invalid_value_error(
    value: Any, allowed: Any, where: str | None, hint: str
) -> ValueError:
    subject = f"socket '{where}'" if where else "this input"
    return ValueError(
        f"Invalid value for {subject}.\n"
        f"  Input should be {format_allowed_values(allowed)}. Got {value!r}.\n"
        f"  {hint}"
    )


def canonical_enum_member(
    value: Any,
    cls: type,
    *,
    allowed: Any = None,
    where: str | None = None,
) -> Any:
    """Return the ``cls`` member ``value`` names, raising if it names none.

    A member of ``cls``, a member of any other ``Enum`` carrying the same
    value, and a bare member value all name the same member: membership is
    decided by value, because serialization keeps only the value. ``allowed``,
    when given, restricts the result to that subset of member values.
    """
    permitted = [member.value for member in cls] if allowed is None else list(allowed)
    value = untagged(value)
    if isinstance(value, cls):
        member = value
    else:
        try:
            member = cls(literal_value(value))
        except (ValueError, KeyError, TypeError):
            example = next(iter(cls.__members__), None)
            named = f" ({cls.__name__}.{example})" if example else ""
            raise _invalid_value_error(
                value,
                permitted,
                where,
                f"{structured_type_path(cls)} members are accepted by "
                f"member{named} or by value.",
            ) from None
    if not value_is_allowed(member.value, permitted):
        raise _invalid_value_error(
            value,
            permitted,
            where,
            f"The socket admits only part of {structured_type_path(cls)}.",
        )
    return member


def canonical_literal_value(
    value: Any,
    allowed: Any,
    *,
    where: str | None = None,
) -> Any:
    """Return ``value`` when it is one of ``allowed``, raising otherwise.

    Matching follows typing's rule that ``True`` is not ``1``: a value matches
    only a candidate of its own type. An ``Enum`` member matches by its value.
    """
    candidate = literal_value(untagged(value))
    if value_is_allowed(candidate, allowed):
        return candidate
    raise _invalid_value_error(
        value, allowed, where, "Only the values listed above are accepted here."
    )


def canonical_socket_value(
    value: Any,
    *,
    structured_type: Dict[str, str] | None = None,
    allowed: Any = None,
    where: str | None = None,
) -> Any:
    """Return the value a socket may store, raising when the socket forbids it.

    ``value`` comes back untouched when the socket constrains nothing.
    """
    if structured_type is not None and structured_type.get("kind") == "enum":
        cls = import_structured_type(structured_type["path"])
        return canonical_enum_member(value, cls, allowed=allowed, where=where)
    if allowed is not None:
        return canonical_literal_value(value, allowed, where=where)
    return value


def coerce_structured_value(value: Any, info: Dict[str, str] | None) -> Any:
    """Rebuild a structured instance from a flat value when spec says so."""
    if info is None:
        return value
    kind = info.get("kind")
    # Enum check goes before the dict gate: its serialized form is a bare value,
    # so an already-materialized-instance/dict short-circuit would never fire.
    # Assignment already decided membership, so this only rebuilds the member.
    if kind == "enum":
        cls = import_structured_type(info["path"])
        return canonical_enum_member(value, cls)
    if is_structured_instance(value):
        return value
    if not isinstance(value, dict):
        return value
    # Only import the target class once we know we must rebuild from a dict.
    # Imports of already-materialized instances (e.g. locally-defined types
    # whose qualname is not importable) must not reach here.
    cls = import_structured_type(info["path"])
    if kind == "pydantic":
        if contains_tagged_value(value):
            if hasattr(cls, "model_construct"):
                return cls.model_construct(**value)
            return cls(**value)
        if hasattr(cls, "model_validate"):
            return cls.model_validate(value)
        return cls(**value)
    if kind == "dataclass":
        return cls(**value)
    return value


def coerce_inputs_from_spec(values: Any, spec: Any) -> Any:
    """Coerce dict inputs into structured instances based on spec metadata."""
    if not isinstance(values, dict):
        return values
    try:
        from node_graph.socket_spec import SocketSpec
    except Exception:
        return values
    spec_obj = spec if isinstance(spec, SocketSpec) else SocketSpec.from_dict(spec)
    out = dict(values)
    for name, child in (spec_obj.fields or {}).items():
        if name not in out:
            continue
        info = child.meta.extras.get("structured_type")
        if info:
            out[name] = coerce_structured_value(out[name], info)
            continue
        if child.is_namespace() and isinstance(out[name], dict):
            out[name] = coerce_inputs_from_spec(out[name], child)
    return out


def contains_tagged_value(value: Any) -> bool:
    """Return True if any TaggedValue appears in the structure."""
    from node_graph.socket import TaggedValue

    if isinstance(value, TaggedValue):
        return True
    if isinstance(value, BaseModel):
        return any(
            contains_tagged_value(getattr(value, name)) for name in value.model_fields
        )
    if is_dataclass(value) and not isinstance(value, type):
        for field in value.__dataclass_fields__.values():
            if contains_tagged_value(getattr(value, field.name)):
                return True
        return False
    if isinstance(value, dict):
        return any(contains_tagged_value(v) for v in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(contains_tagged_value(v) for v in value)
    return False
