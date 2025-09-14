import pytest
from node_graph import NodeGraph, NodePool
from node_graph.socket_spec import namespace as ns


def test_builtin_nodes() -> None:
    """Test builtin nodes of a node graph."""
    ng = NodeGraph(inputs=ns(x=int, y=int), outputs=ns(result=int))
    assert len(ng.nodes) == 3
    assert ng.inputs._metadata.dynamic is False
    assert ng.outputs._metadata.dynamic is False
    assert ng.ctx._metadata.dynamic is True
    assert ng.ctx._metadata.sub_socket_default_link_limit == 1000000
    assert len(ng.inputs) == 2
    assert len(ng.outputs) == 1


def test_ctx() -> None:
    """Test the ctx of a node graph."""
    from node_graph.socket import NodeSocketNamespace

    ng = NodeGraph(name="test_ctx")
    ng.ctx = {"x": 1.0, "y": 2.0}
    node1 = ng.add_node(NodePool.node_graph.test_add, "add1", x=1, y=ng.ctx.y)
    ng.ctx.sum = node1.outputs.result
    node2 = ng.add_node(
        NodePool.node_graph.test_add, "add2", x=2, y=node1.outputs.result
    )
    ng.ctx.sum = node2.outputs.result
    assert len(ng.ctx.sum._links) == 2
    # assign a namespace socket to the ctx
    ng.ctx.node1 = node1.outputs
    assert isinstance(ng.ctx.node1, NodeSocketNamespace)


def test_link() -> None:
    """Test the group inputs and outputs of a node graph."""
    ng = NodeGraph(name="test_inputs_outputs")
    ng.inputs = {"x": 1.0, "y": 2.0}
    node1 = ng.add_node(NodePool.node_graph.test_add, "add1", x=ng.inputs.x)
    ng.add_node(
        NodePool.node_graph.test_add,
        "add2",
        x=ng.inputs.y,
        y=node1.outputs.result,
    )
    ng.outputs.sum = ng.nodes.add2.outputs.result
    assert len(ng.nodes) == 5
    assert len(ng.links) == 4


def test_from_dict() -> None:
    """Test the group inputs and outputs of a node graph."""
    ng = NodeGraph(
        name="test_inputs_outputs",
        inputs=ns(x=float),
        outputs=ns(sum1=float, sum2=float),
    )
    ng.inputs = {"x": 1.0}
    ng.ctx = {"y": 2.0}
    node1 = ng.add_node(NodePool.node_graph.test_add, "add1", x=ng.inputs.x)
    ng.ctx.sum1 = node1.outputs.result
    ng.outputs.sum1 = ng.ctx.sum1
    ng.add_node(
        NodePool.node_graph.test_add,
        "add2",
        x=ng.ctx.y,
        y=node1.outputs.result,
    )
    ng.outputs.sum2 = ng.nodes.add2.outputs.result
    assert len(ng.links) == 6
    ng.to_dict()
    ng1 = NodeGraph.from_dict(ng.to_dict())
    assert len(ng1.nodes) == 5
    assert len(ng1.links) == 6
    assert ng1.ctx.y.value == 2.0
    # add non-existing input will raise an error
    with pytest.raises(ValueError, match="Invalid assignment into namespace socket:"):
        ng1.inputs.z = 3.0


def test_from_dict_dynamic_inputs_outputs() -> None:
    """Test the group inputs and outputs of a node graph."""
    ng = NodeGraph(name="test_inputs_outputs")
    ng.inputs = {"x": 1.0}
    ng.ctx = {"y": 2.0}
    node1 = ng.add_node(NodePool.node_graph.test_add, "add1", x=ng.inputs.x)
    ng.ctx.sum1 = node1.outputs.result
    ng.outputs.sum1 = ng.ctx.sum1
    ng.add_node(
        NodePool.node_graph.test_add,
        "add2",
        x=ng.ctx.y,
        y=node1.outputs.result,
    )
    ng.outputs.sum2 = ng.nodes.add2.outputs.result
    assert len(ng.links) == 6
    ng.to_dict()
    ng1 = NodeGraph.from_dict(ng.to_dict())
    assert len(ng1.nodes) == 5
    assert len(ng1.links) == 6
    assert ng1.ctx.y.value == 2.0
    # add non-existing input will not raise an error
    ng1.inputs.z = 3.0


def test_expose_inputs_outputs() -> None:
    """Test the group inputs and outputs of a node graph."""
    ng = NodeGraph(name="test_inputs_outputs")
    node1 = ng.add_node(NodePool.node_graph.test_add, "add1", x=1)
    ng.add_node(NodePool.node_graph.test_add, "add2", x=2, y=node1.outputs.result)
    with pytest.raises(
        ValueError,
        match="Node add2 does not have inputs spec, cannot expose",
    ):
        ng.expose_inputs()
