from typing import Any, Annotated

from rdflib.namespace import RDFS

from node_graph import Graph, namespace, task
from node_graph.knowledge_graph import KnowledgeGraph
from node_graph.semantics import attach_semantics, serialize_semantics_buffer


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
