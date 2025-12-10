import json
from typing import Any, Annotated

from rdflib import Literal, URIRef
from rdflib.namespace import RDFS

from node_graph import Graph, namespace, task
from node_graph.socket_spec import meta
from node_graph.knowledge_graph import KnowledgeGraph
from node_graph.semantics import (
    SemanticsAnnotation,
    SemanticsPayload,
    SemanticsRelation,
    _SocketRef,
    attach_semantics,
)


@task()
def emit(value):
    return value


@task.graph()
def kg_graph() -> Annotated[dict, namespace(out=Any)]:
    return {"out": emit(value=1).result}


spec_semantics = meta(
    semantics={
        "label": "Spec-labelled output",
        "iri": "ex:Thing",
        "rdf_types": ["ex:Type"],
        "context": {"ex": "http://example.org/"},
        "attributes": {"ex:unit": "ex:EV"},
    }
)


@task()
def spec_annotated() -> Annotated[int, spec_semantics]:
    return 1


@task.graph()
def kg_update_graph_with_spec() -> Annotated[dict, namespace(out=Any)]:
    return {"out": spec_annotated().result}


def test_knowledge_graph_builds_rdflib():
    graph = kg_graph.build()
    socket = graph.tasks["emit"].outputs.result
    attach_semantics(socket, semantics={"label": "Sample output", "iri": "qudt:Energy"})

    rdf = graph.knowledge_graph.as_rdflib()
    labels = {str(obj) for obj in rdf.objects(None, RDFS.label)}

    assert "Sample output" in labels
    assert any("qudt" in str(prefix) for prefix, _ in rdf.namespaces())


def test_knowledge_graph_serialization_roundtrip():
    graph = Graph(name="kg-roundtrip")
    payload = graph.knowledge_graph.to_dict()

    rebuilt = KnowledgeGraph.from_dict(payload, graph_uuid=graph.uuid)
    assert rebuilt.links == payload["triples"]


def test_knowledge_graph_graphviz_available():
    graph = kg_graph.build()
    socket = graph.tasks["emit"].outputs.result
    attach_semantics(socket, semantics={"label": "Viz sample"})
    graph.knowledge_graph.as_rdflib()

    dot = graph.knowledge_graph.to_graphviz()
    assert "KnowledgeGraph" in dot.source


def test_knowledge_graph_to_html():
    graph = kg_graph.build()
    socket = graph.tasks["emit"].outputs.result
    attach_semantics(socket, semantics={"label": "HTML sample"})
    graph.knowledge_graph.as_rdflib()

    html = graph.knowledge_graph.to_html(title="KG HTML")
    assert "<svg" in html and "KG HTML" in html


def test_knowledge_graph_html_variants_share_controls():
    graph = kg_graph.build()
    socket = graph.tasks["emit"].outputs.result
    attach_semantics(socket, semantics={"label": "HTML controls"})
    graph.knowledge_graph.as_rdflib()
    graph.knowledge_graph.graph_uuid = "shared-controls"

    html_doc = graph.knowledge_graph.to_html(title="KG HTML Controls")
    repr_html = graph.knowledge_graph._repr_html_()

    assert repr_html is not None
    control_ids = [
        "kg-shared-controls-zin",
        "kg-shared-controls-zout",
        "kg-shared-controls-reset",
        "kg-shared-controls-fs",
    ]
    for control_id in control_ids:
        assert control_id in html_doc
        assert control_id in repr_html
    zoom_snippet = "container.addEventListener('wheel', onWheel, { passive: false });"
    assert zoom_snippet in html_doc and zoom_snippet in repr_html


def test_knowledge_graph_save_html(tmp_path):
    graph = kg_graph.build()
    socket = graph.tasks["emit"].outputs.result
    attach_semantics(socket, semantics={"label": "Save HTML"})
    graph.knowledge_graph.as_rdflib()

    out_path = tmp_path / "kg.html"
    saved = graph.knowledge_graph.save_html(out_path, title="Saved KG")

    assert saved == str(out_path)
    assert out_path.exists()
    content = out_path.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in content
    assert "Saved KG" in content


def test_knowledge_graph_copy_preserves_state():
    graph = kg_graph.build()
    socket = graph.tasks["emit"].outputs.result
    attach_semantics(socket, semantics={"label": "Copy buffer"})
    graph.knowledge_graph.as_rdflib()
    graph.knowledge_graph.add_namespace("ex", "http://example.org/")

    clone = graph.knowledge_graph.copy(graph_uuid="clone-id")

    assert clone.graph_uuid == "clone-id"
    assert clone.namespaces["ex"] == "http://example.org/"
    assert {"relations": clone.links, "payloads": clone.entities} == {
        "relations": graph.knowledge_graph.links,
        "payloads": graph.knowledge_graph.entities,
    }
    assert clone.entities is not graph.knowledge_graph.entities
    assert clone.links is not graph.knowledge_graph.links


def test_knowledge_graph_add_namespace_binds_cached_graph():
    graph = kg_graph.build()
    graph.knowledge_graph.as_rdflib()
    rdf1 = graph.knowledge_graph.as_rdflib()
    assert dict(rdf1.namespace_manager.namespaces()).get("ex") is None

    graph.knowledge_graph.add_namespace("ex", "http://example.org/")
    rdf2 = graph.knowledge_graph.as_rdflib()

    assert str(dict(rdf2.namespace_manager.namespaces())["ex"]) == "http://example.org/"


def test_knowledge_graph_add_relation_populates_graph_and_context():
    kg = KnowledgeGraph(graph_uuid="g", namespaces={"ex": "http://example.org/"})
    ref = _SocketRef(
        graph_uuid="g", task_name="task", socket_path="result", kind="output"
    )
    relation = SemanticsRelation(
        predicate="ex:relatedTo",
        subject=ref,
        values=("http://target.example/resource", "ctx:Thing"),
        label="Rel label",
        context={"ctx": "http://ctx.example/"},
        socket_label=None,
    )

    kg.add_relation(relation)
    rdf = kg.as_rdflib()

    subj = kg._to_uri("task.output.result")
    pred = kg._to_uri("ex:relatedTo")
    assert (subj, pred, URIRef("http://target.example/resource")) in rdf
    assert (subj, pred, URIRef("http://ctx.example/Thing")) in rdf
    assert (subj, RDFS.label, Literal("Rel label")) in rdf
    assert str(dict(rdf.namespace_manager.namespaces())["ctx"]) == "http://ctx.example/"


def test_knowledge_graph_literal_or_ref_resolves_values():
    kg = KnowledgeGraph(namespaces={"ex": "http://example.org/"})
    socket_ref = _SocketRef(
        graph_uuid="g", task_name="t", socket_path="out", kind="output"
    )

    assert kg._literal_or_ref(socket_ref) == kg._socket_uri(socket_ref)
    assert kg._literal_or_ref("ex:item") == kg._to_uri("ex:item")
    assert kg._literal_or_ref("plain") == Literal("plain")
    list_literal = kg._literal_or_ref(["a", "b"])
    assert isinstance(list_literal, Literal)
    assert json.loads(str(list_literal)) == ["a", "b"]


def test_knowledge_graph_add_payload_populates_links_and_context():
    kg = KnowledgeGraph(graph_uuid="g")
    subject = _SocketRef(
        graph_uuid="g", task_name="producer", socket_path="out", kind="output"
    )
    target = _SocketRef(
        graph_uuid="g", task_name="consumer", socket_path="in", kind="input"
    )
    annotation = SemanticsAnnotation.from_raw(
        {
            "label": "Annotated socket",
            "iri": "ex:Thing",
            "rdf_types": ["ex:Type"],
            "attributes": {"ex:attr": ["foo", "foo"]},
            "relations": {"ex:rel": target},
            "context": {"ex": "http://example.org/"},
        }
    )
    payload = SemanticsPayload(
        subject=subject, semantics=annotation, socket_label="Socket label"
    )

    kg.add_payload(payload)

    assert kg.namespaces["ex"] == "http://example.org/"
    assert kg.entities["producer.output.out"]["label"] == "Socket label"
    assert "consumer.input.in" in kg.entities  # ensured via relations
    assert set(map(tuple, kg.links)) == {
        ("producer.output.out", "rdfs:label", "Socket label"),
        ("producer.output.out", "rdfs:label", "Annotated socket"),
        ("producer.output.out", "rdf:type", "ex:Thing"),
        ("producer.output.out", "rdf:type", "ex:Type"),
        ("producer.output.out", "ex:attr", "foo"),
        ("producer.output.out", "ex:rel", "consumer.input.in"),
    }


def test_knowledge_graph_add_relation_tracks_sockets_and_context():
    kg = KnowledgeGraph()
    subject = _SocketRef(
        graph_uuid="g", task_name="upstream", socket_path="result", kind="output"
    )
    target = _SocketRef(
        graph_uuid="g", task_name="downstream", socket_path="param", kind="input"
    )
    relation = SemanticsRelation(
        predicate="ex:linkedTo",
        subject=subject,
        values=(target, "literal"),
        label="Relation label",
        context={"ex": "http://example.org/"},
        socket_label="Upstream label",
    )

    kg.add_relation(relation)

    assert kg.namespaces["ex"] == "http://example.org/"
    assert kg.entities["upstream.output.result"]["label"] == "Upstream label"
    assert "downstream.input.param" in kg.entities
    assert set(map(tuple, kg.links)) == {
        ("upstream.output.result", "ex:linkedTo", "downstream.input.param"),
        ("upstream.output.result", "ex:linkedTo", "literal"),
        ("upstream.output.result", "rdfs:label", "Upstream label"),
        ("upstream.output.result", "rdfs:label", "Relation label"),
    }


def test_knowledge_graph_update_collects_semantics_from_graph_tasks():
    graph = kg_update_graph_with_spec.build()
    kg = graph.knowledge_graph

    kg.update()

    assert kg.namespaces["ex"] == "http://example.org/"
    assert (
        kg.entities["spec_annotated.output.result"]["label"] == "Spec-labelled output"
    )
    links = set(map(tuple, kg.links))
    assert ("spec_annotated.output.result", "rdf:type", "ex:Thing") in links
    assert ("spec_annotated.output.result", "rdf:type", "ex:Type") in links
    assert ("spec_annotated.output.result", "ex:unit", "ex:EV") in links


def test_knowledge_graph_triples_from_entries_deduplicates_and_serializes_refs():
    kg = KnowledgeGraph()
    target_ref = _SocketRef(
        graph_uuid="g", task_name="target", socket_path="out", kind="output"
    )
    entries = {
        ("task", "output", "result"): {
            "annotation": SemanticsAnnotation(
                label="Annotation label",
                rdf_types=("ex:Type",),
                attributes={"ex:attr": ["dup", "dup"]},
                relations={"ex:rel": target_ref},
            ),
            "socket_label": "Socket label",
        }
    }

    triples = kg._triples_from_entries(entries)

    assert triples[0] == ["task.output.result", "rdfs:label", "Socket label"]
    assert ["task.output.result", "rdfs:label", "Annotation label"] in triples
    assert ["task.output.result", "ex:attr", "dup"] in triples
    assert ["task.output.result", "ex:rel", "target.output.out"] in triples
    assert len([t for t in triples if t[1] == "ex:attr"]) == 1


def test_knowledge_graph_from_dict_handles_semantics_payload():
    payload = {
        "semantics": {
            "sockets": {
                "task.output.out": {
                    "task": "task",
                    "direction": "output",
                    "port": "out",
                }
            },
            "triples": [["task.output.out", "rdfs:label", "Label"]],
        }
    }

    kg = KnowledgeGraph.from_dict(payload, graph_uuid="graph-id")

    assert kg.graph_uuid == "graph-id"
    assert kg.entities["task.output.out"]["task"] == "task"
    assert kg.links == [["task.output.out", "rdfs:label", "Label"]]
    assert kg._dirty is False
