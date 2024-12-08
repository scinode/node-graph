import pytest
import numpy as np
from node_graph import NodeGraph
from node_graph.node import Node


def test_metadata():
    ng = NodeGraph(name="test_base_socket_type")
    n = ng.add_node(Node, "test")
    socket = n.add_input(
        "node_graph.any",
        "test",
        arg_type="kwargs",
        metadata={"dynamic": True},
        link_limit=100000,
        property_data={"default": 1},
    )
    assert socket.metadata == {"dynamic": True}
    assert socket.arg_type == "kwargs"
    assert socket.link_limit == 100000
    assert socket.property.default == 1
    data = socket.to_dict()
    assert data["metadata"] == {"dynamic": True}
    assert data["arg_type"] == "kwargs"


@pytest.mark.parametrize(
    "id, data",
    (
        ("node_graph.int", 1),
        ("node_graph.float", 1.0),
        ("node_graph.bool", False),
        ("node_graph.string", "a"),
        ("node_graph.base_dict", {"a": 1}),
        ("node_graph.base_list", [1, 2, 3]),
    ),
)
def test_base_socket_type(id, data):
    """Test base type socket.
    Should be able to set the correct value to socket's property."""

    ng = NodeGraph(name="test_base_socket_type")
    n = ng.add_node("node_graph.test_add", "test")
    socket = n.add_input(id, id)
    socket.property.value = data
    assert socket.property.value == data
    # copy
    socket1 = socket.copy()
    assert socket1.property.value == data
    # set value directly
    socket1.value = data


@pytest.mark.parametrize(
    "id, data",
    (
        ("node_graph.int", "a"),
        ("node_graph.float", "a"),
        ("node_graph.bool", "a"),
        ("node_graph.string", 0.0),
        ("node_graph.base_dict", 0.0),
        ("node_graph.base_list", 0.0),
    ),
)
def test_base_socket_type_validation(id, data):
    """Test base type socket.
    Should raise a error when the input data is not
    the same type as the socket."""

    ng = NodeGraph(name="test_base_socket_type")
    n = ng.add_node("node_graph.test_add", "test")
    socket = n.add_input(id, id)
    try:
        socket.property.value = data
    except Exception as e:
        print(e)
        assert e is not None
    assert socket.property.value != data


def test_general_socket_property():

    ng = NodeGraph(name="test_base_socket_type")
    n = ng.add_node(Node, "test")
    socket = n.add_input("node_graph.any", "test")
    socket.property.value = np.ones((3, 3))
    assert np.isclose(socket.property.value, np.ones((3, 3))).all()
    # copy
    socket1 = socket.copy()
    assert np.isclose(socket1.property.value, np.ones((3, 3))).all()


def test_socket_match(ng):
    """Test simple math."""

    ng = NodeGraph(name="test_socket_match")
    str1 = ng.add_node("node_graph.test_string", "str1", value="abc")
    math1 = ng.add_node("node_graph.test_add", "math")
    try:
        ng.add_link(str1.outputs[0], math1.inputs[1])
    except Exception as e:
        print(e)
    # the link will fails.
    assert len(ng.links) == 0


def test_repr():
    """Test __repr__ method."""
    ng = NodeGraph(name="test_repr")
    node = ng.add_node("node_graph.test_add", "node1")
    assert repr(node.inputs) == 'InputCollection(node = "node1", sockets = ["x", "y"])'
    assert (
        repr(node.outputs)
        == 'OutputCollection(node = "node1", sockets = ["result", "_outputs"])'
    )
