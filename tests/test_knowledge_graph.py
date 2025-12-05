import json
from typing import Any, Annotated

from rdflib import Literal, URIRef
from rdflib.namespace import RDFS

from node_graph import Graph, namespace, task
from node_graph.knowledge_graph import KnowledgeGraph
from node_graph.semantics import (
    SemanticsRelation,
    _SocketRef,
    attach_semantics,
    serialize_semantics_buffer,
)


@task()
def emit(value):
    return value


@task.graph()
def kg_graph() -> Annotated[dict, namespace(out=Any)]:
    return {"out": emit(value=1).result}


def test_knowledge_graph_builds_rdflib():
    graph = kg_graph.build()
    socket = graph.tasks["emit"].outputs.result
    attach_semantics(socket, semantics={"label": "Sample output", "iri": "qudt:Energy"})

    rdf = graph.knowledge_graph.build_from_graph(graph)
    labels = {str(obj) for obj in rdf.objects(None, RDFS.label)}

    assert "Sample output" in labels
    assert any("qudt" in str(prefix) for prefix, _ in rdf.namespaces())


def test_knowledge_graph_serialization_roundtrip():
    graph = Graph(name="kg-roundtrip")
    graph.knowledge_graph.semantics_buffer = {"relations": [], "payloads": []}
    payload = graph.knowledge_graph.to_dict()

    rebuilt = KnowledgeGraph.from_dict(payload, graph_uuid=graph.uuid)
    assert (
        serialize_semantics_buffer(rebuilt.semantics_buffer)
        == payload["semantics_buffer"]
    )


def test_knowledge_graph_graphviz_available():
    graph = kg_graph.build()
    socket = graph.tasks["emit"].outputs.result
    attach_semantics(socket, semantics={"label": "Viz sample"})
    graph.knowledge_graph.build_from_graph(graph)

    dot = graph.knowledge_graph.to_graphviz()
    assert "KnowledgeGraph" in dot.source


def test_knowledge_graph_to_html():
    graph = kg_graph.build()
    socket = graph.tasks["emit"].outputs.result
    attach_semantics(socket, semantics={"label": "HTML sample"})
    graph.knowledge_graph.build_from_graph(graph)

    html = graph.knowledge_graph.to_html(title="KG HTML")
    assert "<svg" in html and "KG HTML" in html


def test_knowledge_graph_html_variants_share_controls():
    graph = kg_graph.build()
    socket = graph.tasks["emit"].outputs.result
    attach_semantics(socket, semantics={"label": "HTML controls"})
    graph.knowledge_graph.build_from_graph(graph)
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
    graph.knowledge_graph.build_from_graph(graph)

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
    graph.knowledge_graph.build_from_graph(graph)
    graph.knowledge_graph.add_namespace("ex", "http://example.org/")

    clone = graph.knowledge_graph.copy(graph_uuid="clone-id")

    assert clone.graph_uuid == "clone-id"
    assert clone.namespaces["ex"] == "http://example.org/"
    assert serialize_semantics_buffer(
        clone.semantics_buffer
    ) == serialize_semantics_buffer(graph.knowledge_graph.semantics_buffer)
    assert clone.semantics_buffer is not graph.knowledge_graph.semantics_buffer


def test_knowledge_graph_add_namespace_binds_cached_graph():
    graph = kg_graph.build()
    graph.knowledge_graph.build_from_graph(graph)
    rdf1 = graph.knowledge_graph.as_rdflib()
    assert dict(rdf1.namespace_manager.namespaces()).get("ex") is None

    graph.knowledge_graph.add_namespace("ex", "http://example.org/")
    rdf2 = graph.knowledge_graph.as_rdflib()

    assert str(dict(rdf2.namespace_manager.namespaces())["ex"]) == "http://example.org/"


def test_knowledge_graph_add_relation_populates_graph_and_context():
    kg = KnowledgeGraph(graph_uuid="g", namespaces={"ex": "http://example.org/"})
    rdf = kg.as_rdflib()
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

    kg._add_relation(rdf, relation)

    subj = kg._socket_uri(ref)
    pred = kg._to_uri("ex:relatedTo")
    assert (subj, pred, URIRef("http://target.example/resource")) in rdf
    assert (subj, pred, Literal("ctx:Thing")) in rdf
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
