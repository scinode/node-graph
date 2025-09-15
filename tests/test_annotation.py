import types
import pytest
from typing import Any, Optional, Union

from node_graph.socket_spec import (
    Annotated,
    get_origin,
    _is_union_origin,
    _is_annotated_type,
    _find_first_annotated,
    _annotated_parts,
    _unwrap_annotated,
    _extract_spec_from_annotated,
    SocketSpecMeta,
    SocketSpec,
    SocketView,
)


def _has_pep604_union() -> bool:
    return hasattr(types, "UnionType")


@pytest.mark.parametrize(
    "tp,expected",
    [
        (Union[int, str], True),
        (list[int], False),
        (dict[str, int], False),
    ],
)
def test_is_union_origin_typing_union(tp: Any, expected: bool):
    origin = get_origin(tp)
    assert _is_union_origin(origin) is expected


@pytest.mark.skipif(
    not _has_pep604_union(), reason="PEP 604 unions not available before Python 3.10"
)
def test_is_union_origin_pep604_union():
    tp = int | str
    origin = get_origin(tp)
    assert _is_union_origin(origin) is True


def test_is_annotated_type_direct():
    T = Annotated[int, SocketSpecMeta("m")]
    assert _is_annotated_type(T) is True
    assert _is_annotated_type(int) is False


def test_find_first_annotated_direct_and_nested_in_union():
    A = Annotated[int, SocketSpecMeta("m1")]
    assert _find_first_annotated(A) is A

    T = Union[str, A]
    found = _find_first_annotated(T)
    assert found is A

    T2 = Optional[A]  # Union[A, NoneType]
    found2 = _find_first_annotated(T2)
    assert found2 is A


@pytest.mark.skipif(
    not _has_pep604_union(), reason="PEP 604 unions not available before Python 3.10"
)
def test_find_first_annotated_nested_in_pep604_union():
    A = Annotated[int, SocketSpecMeta("m")]
    T = str | A
    found = _find_first_annotated(T)
    assert found is A


def test_annotated_parts_base_and_metadata_order():
    m1 = SocketSpecMeta("m1")
    sv = SocketView("sv_spec")
    sp = SocketSpec("plain_spec")

    A = Annotated[int, m1, sv, sp]
    base, metas = _annotated_parts(A)
    assert base is int
    # Order must be preserved
    assert metas[0] is m1
    assert metas[1] is sv
    assert metas[2] is sp


def test_unwrap_annotated_picks_SocketSpecMeta():
    m = SocketSpecMeta(help="testing")
    A = Annotated[int, "x", m, 123]
    base, meta = _unwrap_annotated(A)
    assert base is int
    assert isinstance(meta, SocketSpecMeta)
    assert meta.help == "testing"

    # No Annotated case
    base2, meta2 = _unwrap_annotated(str)
    assert base2 is str and meta2 is None


def test_extract_spec_from_annotated_prefers_SocketView_over_SocketSpec():
    sp = SocketSpec("any")
    sv = SocketView(sp)
    A = Annotated[int, "noise", sv]
    got = _extract_spec_from_annotated(A)
    assert isinstance(got, SocketSpec)
    assert got.identifier == "any"

    # If only SocketSpec present
    B = Annotated[int, sp]
    got2 = _extract_spec_from_annotated(B)
    assert isinstance(got2, SocketSpec)
    assert got2 is sp

    # No spec present
    C = Annotated[int, "meta"]
    assert _extract_spec_from_annotated(C) is None


def test_extract_spec_from_annotated_nested_in_union_and_optional():
    sp = SocketSpec("any")
    sv = SocketView(sp)
    A = Annotated[int, sv]

    T = Union[str, A]
    assert isinstance(_extract_spec_from_annotated(T), SocketSpec)
    T2 = Optional[A]
    assert isinstance(_extract_spec_from_annotated(T2), SocketSpec)
