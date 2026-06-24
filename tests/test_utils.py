import pytest
from node_graph.socket import TaggedValue
from node_graph.socket_spec import validate_socket_data, SocketSpec
from node_graph.utils import adapt_tagged_values


def test_validate_socket_data():
    """Test the validate_socket_data function to ensure it correctly validates socket data."""
    input_list = ["sum", "diff"]
    result = validate_socket_data(input_list)
    assert isinstance(result, SocketSpec)


def _unwrap(obj):
    """Recursively strip TaggedValue proxies so nested structures compare by value.

    Rebuilds with the *actual* container types, so a list silently turned into a
    tuple (or vice versa) fails the equality check downstream.
    """
    if isinstance(obj, TaggedValue):
        return obj.__wrapped__
    if isinstance(obj, dict):
        return {key: _unwrap(value) for key, value in obj.items()}
    if isinstance(obj, (list, tuple)):
        return type(obj)(_unwrap(value) for value in obj)
    return obj


def test_adapt_tagged_values_adapts_value_and_keeps_identity():
    """The wrapped value passes through the adapter; the proxy, its uuid and its
    socket reference are carried over, and the input is left untouched."""
    socket = object()
    original = TaggedValue(7, socket=socket, uuid="fixed-uuid")

    adapted = adapt_tagged_values(original, adapter=lambda value: value + 100)

    assert isinstance(adapted, TaggedValue)  # proxy preserved, not unwrapped
    assert adapted.__wrapped__ == 107  # value passed through the adapter
    assert adapted._uuid == "fixed-uuid"  # identity carried over
    assert adapted._socket is socket  # socket reference carried over
    assert original.__wrapped__ == 7  # input left untouched


@pytest.mark.parametrize(
    "structure, expected",
    [
        pytest.param({"a": TaggedValue(1)}, {"a": 101}, id="dict"),
        pytest.param([TaggedValue(1), 2], [101, 2], id="list-with-plain-leaf"),
        pytest.param((TaggedValue(1),), (101,), id="tuple"),
        pytest.param(
            {"n": {"deep": [TaggedValue(1)]}}, {"n": {"deep": [101]}}, id="nested"
        ),
    ],
)
def test_adapt_tagged_values_recurses_and_preserves_containers(structure, expected):
    """The adapter reaches every TaggedValue leaf at any depth, plain leaves pass
    through unchanged, and the container types (dict/list/tuple) are preserved."""
    assert (
        _unwrap(adapt_tagged_values(structure, adapter=lambda v: v + 100)) == expected
    )
