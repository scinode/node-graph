from node_graph.decorator import create_node_group, build_node
from node_graph.utils import create_node
from node_graph.decorator import node
from node_graph import NodeGraph


def test_build_node():
    """Build node from a callable."""
    ndata = {
        "executor": {"module": "math.sqrt"},
    }
    MyNumpyAdd = build_node(ndata)
    ng = NodeGraph(name="test_create_node")
    ng.nodes.new(MyNumpyAdd, "add1")
    assert len(ng.nodes) == 1
    "x" in ng.nodes[0].inputs.keys()


def test_create_node():
    """Build node on-the-fly."""
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
        "executor": {"module": "numpy.add"},
    }
    MyNumpyAdd = create_node(ndata)
    ng = NodeGraph(name="test_create_node")
    ng.nodes.new(MyNumpyAdd, "add1")
    assert len(ng.nodes) == 1
    assert ng.nodes[0].properties[0].default == 3
    assert ng.nodes[0].inputs[0].property.default == 10


def test_decorator_parameters() -> None:
    """Test passing parameters to decorators."""

    @node(
        inputs=[{"name": "c"}, {"name": "kwargs"}],
        properties=[{"name": "d", "default": 3}],
        outputs=[{"name": "sum"}, {"name": "product"}],
    )
    def test(a, b=1, **kwargs):
        return {"sum": a + b, "product": a * b}

    test1 = test.node()
    assert test1.inputs["kwargs"].link_limit == 1e6
    assert test1.inputs["kwargs"].identifier == "node_graph.namespace"
    # user defined the c input manually
    assert "c" in test1.inputs.keys()
    assert "d" in test1.properties.keys()
    assert set(test1.kwargs) == set(["b", "c", "d"])
    assert "sum" in test1.outputs.keys()
    assert "product" in test1.outputs.keys()


def create_test_node_group():
    ng = NodeGraph()
    add1 = ng.nodes.new("node_graph.test_add", "add1")
    add2 = ng.nodes.new("node_graph.test_add", "add2")
    add3 = ng.nodes.new("node_graph.test_add", "add3")
    ng.links.new(add1.outputs[0], add3.inputs[0])
    ng.links.new(add2.outputs[0], add3.inputs[1])
    ng.group_properties = [
        ("add1.t", "t1"),
        ("add2.t", "t2"),
    ]
    ng.group_inputs = [("add1.x", "x"), ("add2.x", "y")]
    ng.group_outputs = [("add3.result", "result")]
    return ng


MyTestAddGroup = create_node_group(
    {
        "identifier": "MyTestAddGroup",
        "ng": create_test_node_group(),
    }
)


def test_socket(decorated_myadd):
    """Test simple math."""
    n = decorated_myadd.node()
    assert n.inputs["x"].identifier == "node_graph.float"
    assert n.inputs["y"].identifier == "node_graph.float"
    assert n.inputs["t"].property.default == 1


def test_create_node_group():
    """Build node on-the-fly."""

    ng = NodeGraph(name="test_create_node_group")
    ng.nodes.new(MyTestAddGroup, "add1")
    assert len(ng.nodes) == 1


def test_decorator_node(ng_decorator):

    ng = ng_decorator
    ng.name = "test_decorator_node"
    assert len(ng.nodes) == 4
    assert len(ng.links) == 3


def test_decorator_node_group(decorated_myadd, decorated_myadd_group):
    ng = NodeGraph(name="test_decorator_node_group")
    addgroup1 = ng.nodes.new(decorated_myadd_group, "addgroup1", y=9)
    add1 = ng.nodes.new(decorated_myadd, "add1", x=8)
    ng.links.new(add1.outputs["result"], addgroup1.inputs[0])
    assert len(ng.nodes) == 2


def test_decorator_node_in_decorator_node(decorated_myadd, node_with_decorated_node):

    ng = NodeGraph(name="test_decorator_node_in_decorator_node")
    add1 = ng.nodes.new(decorated_myadd, "add1", x=8)
    add2 = ng.nodes.new(node_with_decorated_node, y=9)
    ng.links.new(add1.outputs["result"], add2.inputs[0])
    assert len(ng.nodes) == 2
