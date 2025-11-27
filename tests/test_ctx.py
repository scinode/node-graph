from node_graph.graph import Graph
from node_graph.socket import TaskSocketNamespace
from node_graph.tasks.tests import test_add


def test_ctx_spec_snapshot_roundtrip():
    ng = Graph()
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

    restored = Graph.from_dict(graph_data)
    assert "foo" in restored.ctx._sockets
    assert restored.ctx.foo.value == 1

    assert isinstance(restored.ctx.metrics, TaskSocketNamespace)
    assert restored.ctx.metrics.baz.value == 2
    assert restored.spec.ctx.to_dict() == ng.spec.ctx.to_dict()
    add_task = ng.add_task(test_add, "add1")
    ng.ctx.results = {"value": add_task.outputs.result}
    assert isinstance(ng.ctx.results, TaskSocketNamespace)
    assert "value" in ng.ctx.results
