import pytest
import numpy as np
from node_graph import NodeGraph
from node_graph.collection import group
from node_graph.node import Node
from node_graph.socket import BaseSocket, NodeSocket, NodeSocketNamespace, TaggedValue
from node_graph.nodes.tests import test_add
import operator as op
from node_graph.errors import GraphDeferredIllegalOperationError
from node_graph.nodes.tests import test_string


@pytest.fixture
def future_socket():
    """A future (result) socket from a node; value only known at runtime."""
    ng = NodeGraph(name="illegal_ops")
    add = ng.add_node(test_add, "add")
    # We only need the future socket object; no need to set inputs
    return add.outputs.result


def _setitem(s):
    s[0] = 1


def _delitem(s):
    del s[0]


def test_predicate_socket_creation_and_bool_forbidden(future_socket):
    """Comparisons should produce predicate sockets; using them in boolean context must raise."""
    cond = future_socket > 5  # should yield another future/predicate socket
    assert isinstance(cond, BaseSocket)

    with pytest.raises(GraphDeferredIllegalOperationError) as e:
        if cond:  # triggers __bool__
            pass

    msg = str(e.value)
    assert "Illegal operation on a future value (Socket)" in msg
    # Guidance order: @node.graph first, then If/While zones
    assert "• Wrap logic in a nested @node.graph." in msg


@pytest.mark.parametrize(
    "op",
    [
        lambda s: int(s),
        lambda s: float(s),
        lambda s: complex(s),
        lambda s: round(s),
        lambda s: hash(s),
    ],
)
def test_numeric_casts_and_hash_forbidden(future_socket, op):
    with pytest.raises(GraphDeferredIllegalOperationError):
        op(future_socket)


@pytest.mark.parametrize(
    "op",
    [
        lambda s: len(s),
        lambda s: iter(s),
        lambda s: reversed(s),
        lambda s: (1 in s),  # membership
        lambda s: s[0],  # __getitem__
        _setitem,  # __setitem__
        _delitem,  # __delitem__
    ],
)
def test_container_protocol_forbidden(future_socket, op):
    with pytest.raises(GraphDeferredIllegalOperationError):
        op(future_socket)


@pytest.mark.parametrize(
    "op",
    [
        lambda s: (s & s),
        lambda s: (s | s),
        lambda s: (s ^ s),
        lambda s: (~s),
        lambda s: (s @ s),  # matrix multiply
    ],
)
def test_bitwise_and_matmul_forbidden(future_socket, op):
    with pytest.raises(GraphDeferredIllegalOperationError):
        op(future_socket)


def test_function_like_ctxmgr_async_forbidden(future_socket):

    # context manager
    with pytest.raises(GraphDeferredIllegalOperationError):
        with future_socket:
            pass


@pytest.mark.asyncio
async def test_await_forbidden(future_socket):
    with pytest.raises(GraphDeferredIllegalOperationError):
        await future_socket


def test_numpy_interop_forbidden(future_socket):
    # array coercion
    with pytest.raises(GraphDeferredIllegalOperationError):
        np.array(future_socket)

    # ufunc
    with pytest.raises(GraphDeferredIllegalOperationError):
        np.sin(future_socket)

    # high-level numpy functions should also be blocked via __array_function__ if implemented
    # (keep this one lenient: some NumPy versions call ufuncs under the hood)
    try:
        with pytest.raises(GraphDeferredIllegalOperationError):
            np.stack([future_socket, future_socket])
    except TypeError:
        # If your implementation routes this differently, TypeError is acceptable;
        # the important part is that it does NOT silently coerce.
        pass


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
        graph=ng,
        metadata={"arg_type": "kwargs", "dynamic": True},
        link_limit=100000,
        property={"default": 1},
    )
    assert socket._graph == ng
    assert socket._metadata.dynamic is True
    assert socket._metadata.arg_type == "kwargs"
    assert socket._link_limit == 100000
    assert socket.property.default == 1
    data = socket._to_dict()
    assert data["metadata"] == {
        "required": True,
        "dynamic": True,
        "child_default_link_limit": 1,
        "socket_type": "INPUT",
        "arg_type": "kwargs",
    }


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
    n = ng.add_node(test_add, "test")
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
    n = ng.add_node(test_add, "test")
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
    str1 = ng.add_node(test_string, "str1", value="abc")
    math1 = ng.add_node(test_add, "math")
    with pytest.raises(TypeError, match="Socket type mismatch"):
        ng.add_link(str1.outputs[0], math1.inputs[1])
    assert len(ng.links) == 0


def test_links(ng):
    assert len(ng.nodes.add1.inputs._all_links) == 1


def test_repr():
    """Test __repr__ method."""
    node = Node()
    node.add_input("node_graph.int", "x")
    assert (
        repr(node.inputs)
        == "NodeSocketNamespace(name='inputs', sockets=['_wait', 'x'])"
    )
    assert (
        repr(node.outputs)
        == "NodeSocketNamespace(name='outputs', sockets=['_outputs', '_wait'])"
    )


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
    key = "x 1"
    with pytest.raises(
        ValueError,
        match="spaces are not allowed",
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
    assert set(n.inputs._get_all_keys()) == {
        "_wait",
        "x",
        "non_dynamic",
        "dynamic",
        "non_dynamic.sub",
        "non_dynamic.sub.y",
        "non_dynamic.sub.z",
        "dynamic.x",
    }
    # to_dict
    data = n.inputs._to_dict()
    assert set(data["sockets"].keys()) == set(["_wait", "x", "non_dynamic", "dynamic"])
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


def test_dynamic_namespace_set_value(node_with_namespace_socket):
    n = node_with_namespace_socket
    # dynamic outputs
    n.outputs._set_socket_value(
        {
            "sum": 10,
            "product": 20,
            "dynamic": {
                "item1": {"sum": 1, "product": 2},
                "item2": {"sum": 3, "product": 4},
            },
        }
    )
    assert n.outputs.sum.value == 10
    assert n.outputs.product.value == 20
    assert "item1" in n.outputs.dynamic
    assert n.outputs.dynamic.item1.sum.value == 1


def test_dynamic_namespace_without_explicit_item_creates_nested():
    metadata = {
        "dynamic": True,
        "extras": {
            "identifier": "node_graph.namespace",
            "dynamic": True,
            "item": None,
        },
    }
    ns = NodeSocketNamespace("inputs", metadata=metadata)
    ns._set_socket_value({"payload": {"inner": 1}})
    assert isinstance(ns.payload, NodeSocketNamespace)
    assert ns.payload.inner.value == 1


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


def test_set_namespace_with_nested_key(node_with_namespace_socket):
    n = node_with_namespace_socket
    # use nested key with "."
    data = {
        "x": 2.0,
        "non_dynamic": {"sub": {"y": 5.0, "z": 6.0}},
        "dynamic.x": 2,
        "dynamic.sub.y": 5,
        "dynamic.sub.z": 6.0,
    }
    n.inputs._value = data
    assert n.inputs.dynamic.x.value == 2
    assert n.inputs.dynamic.sub.y.value == 5
    with pytest.raises(
        AttributeError,
        match="NodeSocketNamespace: 'node_graph.node.inputs.non_dynamic.sub' "
        "has no sub-socket 'non_exist'.",
    ):
        # non_dynamic is not dynamic socket, so it will not create the sub socket
        n.inputs.non_dynamic.sub.non_exist.value == 5

    with pytest.raises(ValueError, match="Invalid assignment into namespace socket:"):
        n.inputs._value = 1

    with pytest.raises(
        ValueError, match="Field 'y' is not defined and this namespace is not dynamic."
    ):
        n.inputs._value = {"y": 2}

    with pytest.raises(
        ValueError,
        match="Invalid assignment into namespace socket:",
    ):
        n.inputs.non_dynamic._value = TaggedValue({})


@pytest.mark.parametrize(
    "op, name, ref_result",
    (
        (op.add, "op_add", 6),
        (op.sub, "op_sub", 2),
        (op.mul, "op_mul", 8),
        (op.truediv, "op_truediv", 2),
        (op.floordiv, "op_floordiv", 2),
        (op.mod, "op_mod", 0),
        (op.pow, "op_pow", 16),
    ),
)
def test_operation(op, name, ref_result, decorated_myadd):
    """Test socket operation."""
    print("decorated_myadd: ", decorated_myadd)
    socket1 = decorated_myadd(2, 2)
    socket2 = decorated_myadd(1, 1)
    print("socket1:", socket1)
    print("socket2:", socket2)
    result = op(socket1, socket2)
    assert isinstance(result, BaseSocket)
    assert name in result._node.name
    result._node.set_inputs({"x": 4, "y": 2})
    result = result._node.execute()
    assert result == ref_result
    # test with non-socket value
    result = op(socket1, 2)
    result._node.inputs.x.value = 4
    result = result._node.execute()
    assert result == ref_result
    # test reverse operation
    result = op(4, socket2)
    result._node.inputs.y.value = 2
    result = result._node.execute()
    assert result == ref_result


@pytest.mark.parametrize(
    "op, name, ref_result",
    (
        (op.lt, "op_lt", False),
        (op.gt, "op_gt", True),
        (op.le, "op_le", False),
        (op.ge, "op_ge", True),
        (op.eq, "op_eq", False),
        (op.ne, "op_ne", True),
    ),
)
def test_operation_comparision(op, name, ref_result, decorated_myadd):
    """Test socket comparision operation."""
    socket1 = decorated_myadd(2, 2)
    socket2 = decorated_myadd(1, 1)
    result = op(socket1, socket2)
    assert isinstance(result, BaseSocket)
    assert name in result._node.name
    result._node.set_inputs({"x": 4, "y": 2})
    result = result._node.execute()
    assert result == ref_result
    # test with non-socket value
    result = op(socket1, 2)
    result._node.inputs.x.value = 4
    result = result._node.execute()
    assert result == ref_result
    # test reverse operation
    # note in the comparision operation, there is not reverse operation
    # so the inputs.x will be always the socket
    result = op(4, socket2)
    result._node.inputs.x.value = 2
    result = result._node.execute()
    assert result == ref_result


def test_unpacking():
    s = NodeSocketNamespace("test", metadata={"dynamic": True})
    s._value = {"a": 1, "b": 2}
    a, b = s
    assert a.value == 1
    assert b.value == 2


def test_set_socket_value():
    s = NodeSocketNamespace("test", metadata={"dynamic": True})
    value = {"a": 1, "b": 2}
    s._set_socket_value(value)
    assert s._value == value


def test_set_namespace_attr():
    ng = NodeGraph()
    n = Node(graph=ng)
    s = NodeSocketNamespace("a", node=n, graph=ng, metadata={"dynamic": True})
    # auto create a sub-socket "x"
    s.x = 1
    assert s.x.value == 1
    s1 = NodeSocket("b", node=n, graph=ng)
    s.x = s1
    assert len(s.x._links) == 1
    s.y = s1
    assert s.y.value is None
    assert len(s.y._links) == 1


def test_set_namespace_item():
    ng = NodeGraph()
    n = Node(graph=ng)
    s = NodeSocketNamespace("a", node=n, graph=ng, metadata={"dynamic": True})

    # auto create a sub-socket "x"
    s["x"] = 1
    assert s.x.value == 1
    assert s["x"].value == 1

    s1 = NodeSocket("b", node=n, graph=ng)

    s["x"] = s1
    assert len(s.x._links) == 1
    assert s["x"]._links == s.x._links

    s["y"] = s1
    assert s.y.value is None
    assert s["y"].value is None

    assert len(s.y._links) == 1
    assert s["y"]._links == s.y._links


def test_add_input_spec_with_dotted_name_materializes_runtime_namespace():
    node = Node()
    node.add_input_spec("node_graph.namespace", "metrics")
    node.add_input_spec("node_graph.int", "metrics.score")

    assert "metrics" in node.inputs._sockets
    metrics_ns = node.inputs.metrics
    assert isinstance(metrics_ns, NodeSocketNamespace)
    assert "score" in metrics_ns._sockets
    assert metrics_ns.score._identifier == "node_graph.int"

    metrics_spec = node.spec.inputs.fields["metrics"]
    assert "score" in metrics_spec.fields
    assert metrics_spec.fields["score"].identifier == "node_graph.int"


def test_socket_waiting_on():
    """Test socket waiting_on."""

    ng = NodeGraph(name="test_socket_waiting_on")
    n1 = ng.add_node(test_add)
    n2 = ng.add_node(test_add)
    n3 = ng.add_node(test_add)
    n4 = ng.add_node(test_add)
    n5 = ng.add_node(test_add)
    # left shift
    # wait for socket
    n1.outputs.result >> n5.inputs.x
    # wait for node
    n2.outputs.result >> n5
    # rshift
    n5 << n3.outputs.result
    n5 << n4
    assert len(n5.inputs._wait._links) == 4
    # chaining dependency
    n6 = ng.add_node(test_add)
    n7 = ng.add_node(test_add)
    n8 = ng.add_node(test_add)
    n6 >> n7 >> n8
    assert n8.inputs._wait._links[0].from_node.name == n7.name
    assert n7.inputs._wait._links[0].from_node.name == n6.name
    # chaining dependency
    n9 = ng.add_node(test_add)
    n10 = ng.add_node(test_add)
    n11 = ng.add_node(test_add)
    n11 << n10 << n9
    assert n11.inputs._wait._links[0].from_node.name == n10.name
    assert n10.inputs._wait._links[0].from_node.name == n9.name


def test_socket_group_waiting_on():
    """Test socket group waiting_on."""

    ng = NodeGraph(name="test_socket_group_waiting_on")
    n1 = ng.add_node(test_add)
    n2 = ng.add_node(test_add)
    n3 = ng.add_node(test_add)

    # Test sockets 2 and 3 wait on socket 1
    n1.outputs.result >> group(n2.outputs.result, n3.outputs.result)
    assert len(n2.inputs._wait._links) == 1
    assert n2.inputs._wait._links[0].from_node.name == n1.name
    assert len(n3.inputs._wait._links) == 1
    assert n3.inputs._wait._links[0].from_node.name == n1.name

    # Test socket 3 waits on sockets 1 and 2
    n3.outputs.result << group(n1.inputs._wait, n2.inputs._wait)
    assert len(n3.inputs._wait._links) == 2
    assert n3.inputs._wait._links[0].from_node.name == n1.name
    assert n3.inputs._wait._links[1].from_node.name == n2.name


def test_tagged_value():
    """Test tagged value in socket."""
    from node_graph.utils import tag_socket_value

    ng = NodeGraph(name="test_base_socket_type")
    n = ng.add_node(Node, "test")
    s = NodeSocketNamespace("inputs", node=n, graph=ng, metadata={"dynamic": True})
    # single value
    a = 1
    # nested socket
    b = {"sub_b": 2}
    # list value
    c = [3, 4]
    s._value = {
        "a": a,
        "b": b,
        "c": c,
        "another_a": a,  # the same input are passed to different sockets
    }
    tag_socket_value(s)
    assert isinstance(s.a.value, TaggedValue)
    assert s.a.value._socket._name == "a"
    for link in ng.links:
        print(link.name)
    # assign the value to another socket
    n1 = ng.add_node(Node, "test1")
    s1 = NodeSocketNamespace("inputs", node=n1, graph=ng, metadata={"dynamic": True})
    s1._set_socket_value(s._collect_values(raw=False))
    # this will add link between the two sockets, instead of copying the value
    assert len(ng.links) == 4
    assert "test.a -> test1.a" in ng.links
