import pytest
import numpy as np
from node_graph import NodeGraph
from node_graph.node import Node
from node_graph.socket import BaseSocket
from node_graph.nodes import NodePool
import operator as op


def test_check_identifier():
    n = Node()
    identifier = "node_graph.inta"
    with pytest.raises(
        ValueError,
        match=f"Identifier: {identifier} is not defined. Did you mean",
    ):
        n.add_input(identifier, "x")


def test_metadata():
    ng = NodeGraph(name="test_base_socket_type")
    n = ng.add_node(Node, "test")
    socket = n.add_input(
        "node_graph.any",
        "test",
        metadata={"arg_type": "kwargs", "dynamic": True},
        link_limit=100000,
        property={"default": 1},
    )
    assert socket._metadata == {"dynamic": True, "arg_type": "kwargs"}
    assert socket._link_limit == 100000
    assert socket.property.default == 1
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
    n = ng.add_node(NodePool.node_graph.test_add, "test")
    socket = n.add_input(id, "test")
    socket.property.value = data
    assert socket.property.value == data
    # copy
    socket1 = socket._copy()
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
    n = ng.add_node(NodePool.node_graph.test_add, "test")
    socket = n.add_input(id, "test")
    try:
        socket.property.value = data
    except Exception as e:
        print(e)
        assert e is not None
    assert socket.property.value != data


def test_general_property():

    ng = NodeGraph(name="test_base_socket_type")
    n = ng.add_node(Node, "test")
    socket = n.add_input("node_graph.any", "test")
    socket.property.value = np.ones((3, 3))
    assert np.isclose(socket.property.value, np.ones((3, 3))).all()
    # copy
    socket1 = socket._copy()
    assert np.isclose(socket1.property.value, np.ones((3, 3))).all()


def test_socket_match(ng):
    """Test simple math."""

    ng = NodeGraph(name="test_socket_match")
    str1 = ng.add_node("node_graph.test_string", "str1", value="abc")
    math1 = ng.add_node(NodePool.node_graph.test_add, "math")
    try:
        ng.add_link(str1.outputs[0], math1.inputs[1])
    except Exception as e:
        print(e)
    # the link will fails.
    assert len(ng.links) == 0


def test_links(ng):
    assert len(ng.nodes.add1.inputs._all_links) == 1


def test_repr():
    """Test __repr__ method."""
    node = Node()
    node.add_input("node_graph.int", "x")
    assert repr(node.inputs) == "NodeSocketNamespace(name='inputs', sockets=['x'])"
    assert repr(node.outputs) == "NodeSocketNamespace(name='outputs', sockets=[])"


def test_check_name():
    """Test namespace socket."""
    node = Node()
    node.add_input("node_graph.int", "x")
    key = "x"
    with pytest.raises(
        ValueError,
        match=f"Name '{key}' already exists in the namespace.",
    ):
        node.add_input("node_graph.int", key)
    key = "_value"
    with pytest.raises(
        ValueError,
        match=f"Name '{key}' is reserved by the namespace.",
    ):
        node.add_input("node_graph.int", key)


def test_namespace(node_with_namespace_socket):
    """Test namespace socket."""
    n = node_with_namespace_socket

    with pytest.raises(
        ValueError,
        match="Namespace non_exist_nested does not exist in the socket collection.",
    ):
        n.add_input("node_graph.namespace", "non_exist_nested.x")

    assert n.inputs._value == {
        "x": 1.0,
        "non_dynamic": {"sub": {"y": 1.0}},
        "dynamic": {"x": 1.0},
    }
    assert n.inputs.non_dynamic.sub.y._full_name == "inputs.non_dynamic.sub.y"
    assert n.inputs.non_dynamic.sub.y._scoped_name == "non_dynamic.sub.y"
    # nested keys
    assert n.inputs._get_all_keys() == [
        "x",
        "non_dynamic",
        "dynamic",
        "non_dynamic.sub",
        "non_dynamic.sub.y",
        "non_dynamic.sub.z",
        "dynamic.x",
    ]
    # to_dict
    data = n.inputs._to_dict()
    assert set(data["sockets"].keys()) == set(["x", "non_dynamic", "dynamic"])
    # copy
    inputs = n.inputs._copy()
    assert inputs._value == n.inputs._value


def test_add_namespace_with_socket():
    """Test namespace socket."""
    n = Node()
    sockets = {
        "x": {"identifier": "node_graph.int"},
        "y": {"identifier": "node_graph.namespace"},
    }
    n.add_input("node_graph.namespace", "abc", sockets=sockets)
    n.inputs.abc.x.value = 1
    n.inputs.abc.y._identifier = "node_graph.namespace"


def test_dynamic_namespace(node_with_namespace_socket):
    """Test dynamic namespace socket."""
    n = node_with_namespace_socket
    with pytest.raises(
        ValueError,
        match="Namespace not_exit does not exist in the socket collection.",
    ):
        n.inputs.non_dynamic._new("node_graph.any", "not_exit.sub")
    # this will create the not exist namespace automatically
    n.inputs.dynamic._new("node_graph.any", "not_exit.sub")
    assert "not_exit" in n.inputs.dynamic
    assert "sub" in n.inputs.dynamic.not_exit


def test_set_namespace(node_with_namespace_socket):
    """Test set namespace."""
    n = node_with_namespace_socket
    data = {
        "x": 2.0,
        "non_dynamic": {"sub": {"y": 5.0, "z": 6.0}},
        "dynamic": {"x": 2},
    }
    n.inputs._value = data
    assert n.inputs._value == data
    # set non-exist namespace for dynamic socket
    data = {
        "x": 2.0,
        "non_dynamic": {"sub": {"y": 5.0, "z": 6.0}},
        "dynamic": {"x": 2, "sub": {"y": 5.0, "z": 6.0}},
    }

    n.inputs._value = data
    assert n.inputs._value == data


def test_keys_order():
    node = Node()
    node.add_input("node_graph.int", "e")
    node.add_input("node_graph.int", "d")
    node.add_input("node_graph.int", "a")
    node.add_input("node_graph.int", "c")
    node.add_input("node_graph.int", "b")
    assert node.inputs[1]._name == "d"
    assert node.inputs["d"]._name == "d"
    assert node.inputs[-2]._name == "c"
    assert node.inputs._get_keys() == ["e", "d", "a", "c", "b"]
    del node.inputs["a"]
    assert node.inputs._get_keys() == ["e", "d", "c", "b"]
    del node.inputs[1]
    assert node.inputs._get_keys() == ["e", "c", "b"]
    del node.inputs[[0, 2]]
    assert node.inputs._get_keys() == ["c"]


@pytest.mark.parametrize(
    "op, name",
    (
        (op.add, "op_add"),
        (op.sub, "op_sub"),
        (op.mul, "op_mul"),
        (op.truediv, "op_truediv"),
        (op.floordiv, "op_floordiv"),
        (op.mod, "op_mod"),
        (op.pow, "op_pow"),
        (op.lshift, "op_lshift"),
        (op.rshift, "op_rshift"),
        (op.and_, "op_and"),
        (op.or_, "op_or"),
        (op.xor, "op_xor"),
    ),
)
def test_operation(op, name, decorated_myadd):
    """Test base type socket.
    Should raise a error when the input data is not
    the same type as the socket."""

    result = op(decorated_myadd(1, 2), decorated_myadd(1, 2))
    assert isinstance(result, BaseSocket)
    assert name in result._node.name
