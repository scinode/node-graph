from node_graph import node, namespace
from node_graph.semantics import SemanticsRelation, SemanticsPayload, attach_semantics
from typing import Any, Annotated


@node()
def emit(value):
    return value


@node.graph()
def simple_graph() -> Annotated[dict, namespace(first=Any, second=Any)]:
    first = emit(value=1).result
    second = emit(value=2).result
    return {"first": first, "second": second}


def test_attach_semantics_records_relations():
    graph = simple_graph.build()
    target = graph.nodes["emit"].outputs.result
    source = graph.nodes["emit1"].outputs.result

    attach_semantics("mat:hasProperty", target, source, label="Relation label")

    buffer = graph.semantics_buffer
    assert len(buffer["relations"]) == 1
    rel = buffer["relations"][0]
    assert isinstance(rel, SemanticsRelation)
    assert rel.predicate == "mat:hasProperty"
    assert rel.label == "Relation label"
    assert rel.subject.node_name == "emit"
    assert rel.values[0].node_name == "emit1"
    assert rel.subject.graph_uuid == graph.uuid
    assert rel.values[0].graph_uuid == graph.uuid


def test_attach_semantics_records_payloads():
    graph = simple_graph.build()
    subject = graph.nodes["emit"].outputs.result

    attach_semantics(subject, semantics={"label": "Sample", "iri": "qudt:Energy"})

    buffer = graph.semantics_buffer
    assert len(buffer["payloads"]) == 1
    payload = buffer["payloads"][0]
    assert isinstance(payload, SemanticsPayload)
    assert payload.socket_label is None
    assert payload.semantics["label"] == "Sample"
    assert payload.semantics["iri"] == "qudt:Energy"
    assert payload.subject.node_name == "emit"
    assert payload.subject.graph_uuid == graph.uuid


def test_serialization_roundtrip_preserves_semantics_buffer():
    graph = simple_graph.build()
    subject = graph.nodes["emit"].outputs.result
    attach_semantics(subject, semantics={"label": "Sample"})

    serialized = graph.to_dict()
    rebuilt = type(graph).from_dict(serialized)

    assert rebuilt.semantics_buffer == serialized["semantics_buffer"]
