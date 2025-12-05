from node_graph import Graph
from node_graph.semantics import serialize_semantics_buffer


def test_semantics_buffer_initialized():
    ng = Graph(name="with_semantics")
    assert ng.semantics_buffer == {"relations": [], "payloads": []}


def test_semantics_buffer_roundtrip():
    ng = Graph(name="with_semantics")
    sample = {"relations": [{"predicate": "p"}], "payloads": []}
    ng.semantics_buffer = sample

    payload = ng.to_dict()
    rebuilt = Graph.from_dict(payload)

    rebuilt_buffer = serialize_semantics_buffer(rebuilt.semantics_buffer)
    assert rebuilt_buffer["relations"][0]["predicate"] == "p"
