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
    socket = n.add_input(id, "test")
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
    socket = n.add_input(id, "test")
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
    node = Node()
    node.add_input("node_graph.int", "x")
    assert repr(node.inputs) == "NodeSocketNamespace(name='inputs', sockets=['x'])"
    assert repr(node.outputs) == "NodeSocketNamespace(name='outputs', sockets=[])"


def test_namespace():
    """Test namespace socket."""
    n = Node()

    with pytest.raises(
        ValueError, match="Namespace nested does not exist in the socket collection."
    ):
        n.add_input("node_graph.namespace", "nested.x")
    inp_nest = n.add_input("node_graph.namespace", "nested")
    inp_nest_x = n.add_input("node_graph.float", "nested.x")
    inp_nest_x.value = 1.0
    assert n.inputs.nested.x.value == 1.0
    inp_sub_nested = inp_nest._new("node_graph.namespace", "sub_nested")
    inp_sub_nested_y = inp_sub_nested._new("node_graph.float", "y")
    inp_sub_nested_y.value = 1.0
    assert n.inputs.nested.sub_nested.y.value == 1.0
    assert "nested" in n.inputs
    assert "x" in n.inputs.nested
