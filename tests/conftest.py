import pytest
from node_graph.decorator import node
from node_graph import NodeGraph


@pytest.fixture
def nt():
    """A test node_graph."""
    nt = NodeGraph(name="test_nodetree")
    float1 = nt.nodes.new("TestFloat", "float1", value=3.0)
    add1 = nt.nodes.new("TestAdd", "add1", x=2)
    add2 = nt.nodes.new("TestAdd", "add2", x=2)
    nt.links.new(float1.outputs[0], add1.inputs["y"])
    nt.links.new(add1.outputs[0], add2.inputs["y"])
    return nt


@pytest.fixture
def nt_group():
    nt = NodeGraph(name="test_node_group")
    # auto generate name for the node
    float1 = nt.nodes.new("TestFloat", "float1", value=4.0, t=3)
    float2 = nt.nodes.new("TestFloat", "float2", value=3.0)
    sqrt_power_add1 = nt.nodes.new(
        "TestSqrtPowerAdd", "sqrt_power_add1", t1=3, t2=2, y=3
    )
    add1 = nt.nodes.new("TestAdd", "add1")
    nt.links.new(float1.outputs[0], sqrt_power_add1.inputs[0])
    nt.links.new(float2.outputs[0], sqrt_power_add1.inputs[1])
    nt.links.new(sqrt_power_add1.outputs[0], add1.inputs[1])
    return nt


@pytest.fixture
def decorated_myadd():
    """Generate a decorated node for test."""

    @node(
        identifier="MyAdd",
        properties=[["Float", "t", {"default": 1}]],
        inputs=[["Float", "x"], ["Float", "y"]],
        outputs=[["General", "result"]],
    )
    def myadd(t: float, x: float, y: float):
        return x + y

    return myadd


@pytest.fixture
def decorated_myadd_group(decorated_myadd):
    """Generate a decorated node group for test."""
    myadd = decorated_myadd

    @node.group(identifier="MyAddGroup")
    def myaddgroup():
        nt = NodeGraph()
        add1 = nt.nodes.new(myadd, "add1")
        add1.set({"t": 3, "y": 2})
        add2 = nt.nodes.new(myadd, "add2")
        add2.set({"y": 3})
        add3 = nt.nodes.new(myadd, "add3")
        add3.set({"t": 2})
        nt.links.new(add1.outputs[0], add3.inputs[0])
        nt.links.new(add2.outputs[0], add3.inputs[1])
        nt.group_properties = [
            ("add1.t", "t1"),
            ("add2.t", "t2"),
        ]
        nt.group_inputs = [("add1.x", "x"), ("add2.x", "y")]
        nt.group_outputs = [("add3.result", "result")]
        return nt

    return myaddgroup


@pytest.fixture
def node_with_decorated_node(decorated_myadd):
    """Generate a node with decorated node for test."""

    @node(
        identifier="node_with_decorated_node",
        inputs=[["Float", "x"], ["Float", "y"]],
        outputs=[["General", "result"]],
    )
    def node_with_decorated_node(x, y):
        nt = NodeGraph("node_in_decorated_node")
        add1 = nt.nodes.new(decorated_myadd, x=x)
        add2 = nt.nodes.new(decorated_myadd, y=y)
        nt.links.new(add1.outputs[0], add2.inputs[0])
        nt.launch(wait=True)
        return add2.results[0]["value"]

    return node_with_decorated_node


@pytest.fixture
def nt_decorator(decorated_myadd):
    """A test node_graph."""
    nt = NodeGraph(name="test_decorator_node")
    float1 = nt.nodes.new("TestFloat", "float1", value=3.0)
    add1 = nt.nodes.new(decorated_myadd, "add1", x=2)
    add2 = nt.nodes.new(decorated_myadd, "add2", x=2)
    add3 = nt.nodes.new("TestAdd", "add3")
    nt.links.new(float1.outputs[0], add1.inputs["y"])
    nt.links.new(add1.outputs[0], add2.inputs["y"])
    nt.links.new(add2.outputs[0], add3.inputs[0])
    return nt