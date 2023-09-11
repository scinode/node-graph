import pytest
import numpy as np
from node_graph import NodeGraph


@pytest.mark.parametrize(
    "id, data",
    (
        ("Int", 1),
        ("Float", 1.0),
        ("Bool", False),
        ("String", "a"),
        ("BaseDict", {"a": 1}),
        ("BaseList", [1, 2, 3]),
    ),
)
def test_base_socket_type(id, data):
    """Test base type socket.
    Should be able to set the correct value to socket's property."""

    nt = NodeGraph(name="test_base_socket_type")
    n = nt.nodes.new("TestAdd", "test")
    socket = n.inputs.new(id, id)
    socket.property.value = data
    assert socket.property.value == data
    # copy
    socket1 = socket.copy()
    assert socket1.property.value == data


@pytest.mark.parametrize(
    "id, data",
    (
        ("Int", "a"),
        ("Float", "a"),
        ("Bool", "a"),
        ("String", 0.0),
        ("BaseDict", 0.0),
        ("BaseList", 0.0),
    ),
)
def test_base_socket_type_validation(id, data):
    """Test base type socket.
    Should raise a error when the input data is not
    the same type as the socket."""

    nt = NodeGraph(name="test_base_socket_type")
    n = nt.nodes.new("TestAdd", "test")
    socket = n.inputs.new(id, id)
    try:
        socket.property.value = data
    except Exception as e:
        print(e)
        assert e is not None
    assert socket.property.value != data


def test_general_socket_property():
    from node_graph.node import Node

    nt = NodeGraph(name="test_base_socket_type")
    n = nt.nodes.new(Node, "test")
    socket = n.inputs.new("General", "test")
    socket.property.value = np.ones((3, 3))
    assert np.isclose(socket.property.value, np.ones((3, 3))).all()
    # copy
    socket1 = socket.copy()
    assert np.isclose(socket1.property.value, np.ones((3, 3))).all()


def test_socket_match(nt):
    """Test simple math."""

    nt = NodeGraph(name="test_socket_match")
    str1 = nt.nodes.new("TestString", "str1", value="abc")
    math1 = nt.nodes.new("TestAdd", "math")
    try:
        nt.links.new(str1.outputs[0], math1.inputs[1])
    except Exception as e:
        print(e)
    # the link will fails.
    assert len(nt.links) == 0
