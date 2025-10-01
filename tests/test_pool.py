from node_graph import NodePool, Node
import pytest


def test_node_pool():
    assert "node_graph.test_enum_update" in NodePool
    assert isinstance(NodePool.node_graph.test_enum_update.load()(), Node)
    with pytest.raises(
        AttributeError,
        match="Namespace node_graph has no attribute 'test_add1'",
    ):
        NodePool.node_graph.test_add1
