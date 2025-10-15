from node_graph.node_graph import NodeGraph
from node_graph.socket import NodeSocketNamespace
from node_graph.nodes.tests import test_add


def test_ctx_spec_snapshot_roundtrip():
    ng = NodeGraph()
    # Mutate the ctx namespace at runtime with both leaf and nested values.
    ng.ctx = {"foo": 1, "metrics.baz": 2}

    graph_data = ng.to_dict()
    ctx_spec = graph_data["spec"]["ctx"]

    assert ctx_spec["identifier"] == "node_graph.namespace"
    assert ctx_spec["dynamic"] is True
    assert "foo" in ctx_spec["fields"]
    assert ctx_spec["fields"]["foo"]["identifier"] == "node_graph.any"

    assert "metrics" in ctx_spec["fields"]
    metrics_spec = ctx_spec["fields"]["metrics"]
    assert metrics_spec["identifier"] == "node_graph.namespace"
    assert "baz" in metrics_spec["fields"]
    assert metrics_spec["fields"]["baz"]["identifier"] == "node_graph.any"

    restored = NodeGraph.from_dict(graph_data)
    assert "foo" in restored.ctx._sockets
    assert restored.ctx.foo.value == 1

    assert isinstance(restored.ctx.metrics, NodeSocketNamespace)
    assert restored.ctx.metrics.baz.value == 2
    assert restored.spec.ctx.to_dict() == ng.spec.ctx.to_dict()
    add_node = ng.add_node(test_add, "add1")
    ng.ctx.results = {"value": add_node.outputs.result}
    assert isinstance(ng.ctx.results, NodeSocketNamespace)
    assert "value" in ng.ctx.results
