from node_graph import NodeGraph, node, NodePool
import pytest


def test_from_dict(ng_decorator):
    """Export NodeGraph to dict."""
    ng = ng_decorator
    ntdata = ng_decorator.to_dict()
    ng1 = NodeGraph.from_dict(ntdata)
    assert len(ng.nodes) == len(ng1.nodes)
    assert len(ng.links) == len(ng1.links)
    assert ng.to_dict() == ng1.to_dict()


def test_new_node(ng):
    """Test new node."""
    ng = NodeGraph(name="test_nodegraph")
    n1 = ng.add_node(NodePool.node_graph.test_add)
    n2 = ng.add_node(NodePool.node_graph.test_add)
    assert n1.name == "test_add"
    assert n2.name == "test_add1"
    assert len(ng.nodes) == 2
    # add builtin node is not allowed
    name = "graph_inputs"
    with pytest.raises(
        ValueError,
        match=f"Name {name} can not be used, it is reserved.",
    ):
        ng.add_node(NodePool.node_graph.test_add, name=name)


def test_delete_node(ng):
    """Test delete node."""
    n = len(ng.nodes)
    nlink = len(ng.links)
    ng.add_node(NodePool.node_graph.test_add, name="add3")
    ng.add_link(ng.nodes["add1"].outputs[0], ng.nodes["add3"].inputs["y"])
    assert len(ng.nodes) == n + 1
    assert len(ng.links) == nlink + 1
    ng.delete_nodes(["add3"])
    assert len(ng.nodes) == n
    assert len(ng.links) == nlink


def test_copy(ng):
    """Test copy node graph"""
    n = len(ng.nodes)
    nlink = len(ng.links)
    ng1 = ng.copy()
    assert len(ng1.nodes) == n
    assert len(ng1.links) == nlink


def test_add(ng):
    """Test add another nodegraph."""
    n = len(ng.nodes)
    nlink = len(ng.links)
    ng1 = NodeGraph(name="test_add")
    ng1.add_node(NodePool.node_graph.test_float, "float3", value=4.0, t=3)
    ng1.add_node(NodePool.node_graph.test_float, "float4", value=3.0)
    ng = ng + ng1
    assert len(ng.nodes) == n + 2
    assert len(ng.links) == nlink


def test_copy_subset(ng):
    """Test copy subset of nodes."""
    ng1 = ng.copy_subset(["add1", "add2"])
    assert len(ng1.nodes) == 3
    assert len(ng1.links) == 2
    assert "float1" in ng1.get_node_names()


def test_get_items(ng):
    """Test get items."""
    ng1 = ng[["add1", "add2"]]
    assert len(ng1.nodes) == 3
    assert len(ng1.links) == 2
    assert "float1" in ng1.get_node_names()


def test_load_graph():
    @node(
        inputs={
            "nested": {"identifier": "node_graph.namespace"},
            "nested.d": {},
            "nested.f": {"identifier": "node_graph.namespace"},
            "nested.f.g": {},
            "nested.f.h": {},
        },
        outputs={
            "sum": {},
            "product": {},
            "nested": {"identifier": "node_graph.namespace"},
            "nested.sum": {},
            "nested.product": {},
        },
    )
    def test(a, b=1, nested={}):
        return {
            "sum": a + b,
            "product": a * b,
            "nested": {"sum": a + b, "product": a * b},
        }

    ng = NodeGraph()
    test1 = ng.add_node(test, "test1")
    test1.set(
        {
            "a": 1,
            "b": 2,
            "nested": {"d": 2, "f": {"g": 1, "h": 2}},
        }
    )
    ngdata = ng.to_dict()
    # load graph
    ng1 = NodeGraph.from_dict(ngdata)
    assert "sum" in ng1.nodes.test1.outputs.nested
    assert ng1.nodes.test1.inputs._value == ng.nodes.test1.inputs._value


def test_generate_inputs(ng):
    """Test generation of inputs from nodes"""
    ng.generate_inputs()
    assert ng.inputs.float1._value == ng.nodes["float1"].inputs._value
    assert ng.inputs.add1._value == ng.nodes["add1"].inputs._value
    assert ng.inputs.add2._value == ng.nodes["add2"].inputs._value


def test_generate_inputs_names(ng):
    """Test generation of inputs from named nodes"""
    ng.generate_inputs(names=["float1", "add2"])
    assert ng.inputs.float1._value == ng.nodes["float1"].inputs._value
    assert "add1" not in ng.inputs
    assert ng.inputs.add2._value == ng.nodes["add2"].inputs._value


@pytest.mark.xfail(raises=ValueError)
def test_generate_inputs_names_invalid(ng):
    """Test that input generation fails for invalid name"""
    ng.generate_inputs(names=["missing"])


def test_generate_outputs(ng):
    """Test generation of outputs from nodes"""
    ng.generate_outputs()
    assert ng.outputs.float1._value == ng.nodes["float1"].outputs._value
    assert ng.outputs.add1._value == ng.nodes["add1"].outputs._value
    assert ng.outputs.add2._value == ng.nodes["add2"].outputs._value


def test_generate_outputs_names(ng):
    """Test generation of outputs from named nodes"""
    ng.generate_outputs(names=["add1"])
    assert "float1" not in ng.outputs
    assert ng.outputs.add1._value == ng.nodes["add1"].outputs._value
    assert "add2" not in ng.outputs


@pytest.mark.xfail(raises=ValueError)
def test_generate_outputs_names_invalid(ng):
    """Test that output generation fails for invalid name"""
    ng.generate_outputs(names=["missing"])
