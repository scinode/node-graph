from node_graph.decorator import create_node, create_node_group
from node_graph.decorator import node
from node_graph import NodeGraph

ndata = {
    "identifier": "MyNumpyAdd",
    "properties": [{"identifier": "node_graph.float", "name": "x", "default": 3}],
    "inputs": [
        {
            "identifier": "node_graph.float",
            "name": "y",
            "property": {"identifier": "node_graph.float", "default": 10},
        },
    ],
    "outputs": [{"identifier": "node_graph.any", "name": "result"}],
    "executor": {"path": "numpy.add"},
}
MyNumpyAdd = create_node(ndata)


def test_decorator_parameters() -> None:
    """Test passing parameters to decorators."""

    @node(
        inputs=[{"name": "c"}, {"name": "kwargs", "link_limit": 1000}],
        properties=[{"name": "d", "default": 3}],
        outputs=[{"name": "sum"}, {"name": "product"}],
    )
    def test(a, b=1, **kwargs):
        return {"sum": a + b, "product": a * b}

    test1 = test.node()
    assert test1.inputs["kwargs"].link_limit == 1000
    # user defined the c input manually
    assert "c" in test1.inputs.keys()
    assert "d" in test1.properties.keys()
    assert set(test1.kwargs) == set(["b", "c", "d"])
    assert "sum" in test1.outputs.keys()
    assert "product" in test1.outputs.keys()


def create_test_node_group():
    nt = NodeGraph()
    add1 = nt.nodes.new("node_graph.test_add", "add1")
    add2 = nt.nodes.new("node_graph.test_add", "add2")
    add3 = nt.nodes.new("node_graph.test_add", "add3")
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


def test_socket(decorated_myadd):
    """Test simple math."""
    n = decorated_myadd.node()
    assert n.inputs["x"].identifier == "node_graph.float"
    assert n.inputs["y"].identifier == "node_graph.float"
    assert n.inputs["t"].property.default == 1


def test_create_node():
    """Build node on-the-fly."""

    nt = NodeGraph(name="test_create_node")
    nt.nodes.new(MyNumpyAdd, "add1")
    assert len(nt.nodes) == 1
    assert nt.nodes[0].properties[0].default == 3
    assert nt.nodes[0].inputs[0].property.default == 10


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
