from node_graph.decorator import node, create_node, create_node_group
from node_graph import NodeGraph
import pytest

ndata = {
    "identifier": "MyNumpyAdd",
    "properties": [["Float", "x", {"default": 3}]],
    "inputs": [["Float", "y", {"property": ["Float", {"default": 10}]}]],
    "outputs": [["General", "result"]],
    "executor": {"path": "numpy.add"},
}
MyNumpyAdd = create_node(ndata)


def create_test_node_group():
    nt = NodeGraph()
    add1 = nt.nodes.new("TestAdd", "add1")
    add2 = nt.nodes.new("TestAdd", "add2")
    add3 = nt.nodes.new("TestAdd", "add3")
    nt.links.new(add1.outputs[0], add3.inputs[0])
    nt.links.new(add2.outputs[0], add3.inputs[1])
    nt.group_properties = [
        ("add1.t", "t1"),
        ("add2.t", "t2"),
    ]
    nt.group_inputs = [("add1.x", "x"), ("add2.x", "y")]
    nt.group_outputs = [("add3.result", "result")]
    return nt


MyTestAddGroup = create_node_group(
    {
        "identifier": "MyTestAddGroup",
        "nt": create_test_node_group(),
    }
)


def test_create_node():
    """Build node on-the-fly."""

    nt = NodeGraph(name="test_create_node")
    nt.nodes.new(MyNumpyAdd, "add1")
    assert len(nt.nodes) == 1


def test_create_node_group():
    """Build node on-the-fly."""

    nt = NodeGraph(name="test_create_node_group")
    nt.nodes.new(MyTestAddGroup, "add1")
    assert len(nt.nodes) == 1


def test_decorator_node(nt_decorator):

    nt = nt_decorator
    nt.name = "test_decorator_node"
    assert len(nt.nodes) == 4
    assert len(nt.links) == 3


def test_decorator_node_group(decorated_myadd, decorated_myadd_group):
    nt = NodeGraph(name="test_decorator_node_group")
    addgroup1 = nt.nodes.new(decorated_myadd_group, "addgroup1", y=9)
    add1 = nt.nodes.new(decorated_myadd, "add1", x=8)
    nt.links.new(add1.outputs["result"], addgroup1.inputs[0])
    assert len(nt.nodes) == 2


def test_decorator_node_in_decorator_node(decorated_myadd, node_with_decorated_node):

    nt = NodeGraph(name="test_decorator_node_in_decorator_node")
    add1 = nt.nodes.new(decorated_myadd, "add1", x=8)
    add2 = nt.nodes.new(node_with_decorated_node, y=9)
    nt.links.new(add1.outputs["result"], add2.inputs[0])
    assert len(nt.nodes) == 2
