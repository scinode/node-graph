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
        metadata={"arg_type": "kwargs", "dynamic": True},
        link_limit=100000,
        property_data={"default": 1},
    )
    assert socket.socket_metadata == {"dynamic": True, "arg_type": "kwargs"}
    assert socket.socket_link_limit == 100000
    assert socket.socket_property.default == 1
    data = socket._to_dict()
    assert data["metadata"] == {"dynamic": True, "arg_type": "kwargs"}


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
    socket.socket_property.value = data
    assert socket.socket_property.value == data
    # copy
    socket1 = socket._copy()
    assert socket1.socket_property.value == data
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
        socket.socket_property.value = data
    except Exception as e:
        print(e)
        assert e is not None
    assert socket.socket_property.value != data


def test_general_property():

    ng = NodeGraph(name="test_base_socket_type")
    n = ng.add_node(Node, "test")
    socket = n.add_input("node_graph.any", "test")
    socket.socket_property.value = np.ones((3, 3))
    assert np.isclose(socket.socket_property.value, np.ones((3, 3))).all()
    # copy
    socket1 = socket._copy()
    assert np.isclose(socket1.socket_property.value, np.ones((3, 3))).all()


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


def test_namespace(node_with_namespace_socket):
    """Test namespace socket."""
    n = node_with_namespace_socket

    with pytest.raises(
        ValueError,
        match="Namespace non_exist_nested does not exist in the socket collection.",
    ):
        n.add_input("node_graph.namespace", "non_exist_nested.x")

    assert n.inputs.socket_value == {
        "x": 1.0,
        "non_dynamic": {"sub": {"y": 1.0}},
        "dynamic": {"x": 1.0},
    }


def test_set_namespace(node_with_namespace_socket):
    """Test set namespace."""
    n = node_with_namespace_socket
    data = {
        "x": 2.0,
        "non_dynamic": {"sub": {"y": 5.0, "z": 6.0}},
        "dynamic": {"x": 2},
    }
    n.inputs.socket_value = data
    assert n.inputs.socket_value == data
    # set non-exist namespace for dynamic socket
    data = {
        "x": 2.0,
        "non_dynamic": {"sub": {"y": 5.0, "z": 6.0}},
        "dynamic": {"x": 2, "sub": {"y": 5.0, "z": 6.0}},
    }

    n.inputs.socket_value = data
    assert n.inputs.socket_value == data


def test_keys_order():
    node = Node()
    node.add_input("node_graph.int", "e")
    node.add_input("node_graph.int", "d")
    node.add_input("node_graph.int", "a")
    node.add_input("node_graph.int", "c")
    node.add_input("node_graph.int", "b")
    assert node.inputs[1].socket_name == "d"
    assert node.inputs["d"].socket_name == "d"
    assert node.inputs[-2].socket_name == "c"
    assert node.inputs._keys() == ["e", "d", "a", "c", "b"]
    del node.inputs["a"]
    assert node.inputs._keys() == ["e", "d", "c", "b"]
    del node.inputs[1]
    assert node.inputs._keys() == ["e", "c", "b"]
    del node.inputs[[0, 2]]
    assert node.inputs._keys() == ["c"]
