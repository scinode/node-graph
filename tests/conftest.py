import pytest
from node_graph.decorator import node
from node_graph import NodeGraph


@pytest.fixture
def ng():
    """A test node_graph."""
    ng = NodeGraph(name="test_nodetree")
    float1 = ng.nodes.new("node_graph.test_float", "float1", value=3.0)
    add1 = ng.nodes.new("node_graph.test_add", "add1", x=2)
    add2 = ng.nodes.new("node_graph.test_add", "add2", x=2)
    ng.links.new(float1.outputs[0], add1.inputs["y"])
    ng.links.new(add1.outputs[0], add2.inputs["y"])
    return ng


@pytest.fixture
def ng_group():
    ng = NodeGraph(name="test_node_group")
    # auto generate name for the node
    float1 = ng.nodes.new("node_graph.test_float", "float1", value=4.0, t=3)
    float2 = ng.nodes.new("node_graph.test_float", "float2", value=3.0)
    sqrt_power_add1 = ng.nodes.new(
        "TestSqrtPowerAdd", "sqrt_power_add1", t1=3, t2=2, y=3
    )
    add1 = ng.nodes.new("node_graph.test_add", "add1")
    ng.links.new(float1.outputs[0], sqrt_power_add1.inputs[0])
    ng.links.new(float2.outputs[0], sqrt_power_add1.inputs[1])
    ng.links.new(sqrt_power_add1.outputs[0], add1.inputs[1])
    return ng


@pytest.fixture
def decorated_myadd():
    """Generate a decorated node for test."""

    @node(
        outputs=[{"identifier": "node_graph.any", "name": "result"}],
    )
    def myadd(x: float, y: float, t: float = 1):
        import time

        time.sleep(t)
        return x + y

    return myadd


@pytest.fixture
def decorated_myadd_group(decorated_myadd):
    """Generate a decorated node group for test."""
    myadd = decorated_myadd

    @node.group(outputs=[("add3.result", "result")])
    def myaddgroup(x, y):
        ng = NodeGraph()
        add1 = ng.nodes.new(myadd, "add1")
        add1.set({"t": 3, "x": x, "y": 2})
        add2 = ng.nodes.new(myadd, "add2")
        add2.set({"x": y, "y": 3})
        add3 = ng.nodes.new(myadd, "add3")
        add3.set({"t": 2})
        ng.links.new(add1.outputs[0], add3.inputs[0])
        ng.links.new(add2.outputs[0], add3.inputs[1])
        return ng

    return myaddgroup


@pytest.fixture
def node_with_decorated_node(decorated_myadd):
    """Generate a node with decorated node for test."""

    @node(
        identifier="node_with_decorated_node",
        inputs=[
            {"identifier": "node_graph.float", "name": "x"},
            {"identifier": "node_graph.float", "name": "y"},
        ],
        outputs=[{"identifier": "node_graph.any", "name": "result"}],
    )
    def node_with_decorated_node(x, y):
        ng = NodeGraph("node_in_decorated_node")
        add1 = ng.nodes.new(decorated_myadd, x=x)
        add2 = ng.nodes.new(decorated_myadd, y=y)
        ng.links.new(add1.outputs[0], add2.inputs[0])
        ng.launch(wait=True)
        return add2.results[0]["value"]

    return node_with_decorated_node


@pytest.fixture
def ng_decorator(decorated_myadd):
    """A test node_graph."""
    ng = NodeGraph(name="test_decorator_node")
    float1 = ng.nodes.new("node_graph.test_float", "float1", value=3.0)
    add1 = ng.nodes.new(decorated_myadd, "add1", x=2)
    add2 = ng.nodes.new(decorated_myadd, "add2", x=2)
    add3 = ng.nodes.new("node_graph.test_add", "add3")
    ng.links.new(float1.outputs[0], add1.inputs["y"])
    ng.links.new(add1.outputs[0], add2.inputs["y"])
    ng.links.new(add2.outputs[0], add3.inputs[0])
    return ng
