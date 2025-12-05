"""Knowledge graph helpers built on top of rdflib and graphviz.

This module keeps knowledge-graph responsibilities separate from the core
graph authoring utilities. Semantics captured during graph construction are
normalised into a buffer, mapped into an RDF graph (using rdflib), and can be
visualised via graphviz without the caller having to manipulate either
library directly.
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4
from typing import Any, Dict, Mapping, Optional, Union

from rdflib import Graph as RDFGraph
from rdflib import Literal, Namespace, URIRef
from rdflib.namespace import RDF, RDFS

from node_graph.semantics import (
    SemanticsAnnotation,
    SemanticsPayload,
    SemanticsRelation,
    _SocketRef,
    _normalize_semantics_buffer,
    namespace_registry,
    serialize_semantics_buffer,
)

try:  # Optional dependency used for visualisation
    from graphviz import Digraph
except Exception:  # pragma: no cover - optional import
    Digraph = None


def _default_buffer() -> Dict[str, list]:
    return {"relations": [], "payloads": []}


class KnowledgeGraph:
    """Light-weight container for semantics-backed knowledge graphs."""

    def __init__(
        self,
        *,
        graph_uuid: Optional[str] = None,
        semantics_buffer: Optional[Mapping[str, Any]] = None,
        namespaces: Optional[Mapping[str, str]] = None,
    ) -> None:
        self.graph_uuid = graph_uuid
        self.namespaces: Dict[str, str] = dict(namespaces or namespace_registry())
        self._semantics_buffer = _normalize_semantics_buffer(
            semantics_buffer or _default_buffer()
        )
        self._rdflib_graph: Optional[RDFGraph] = None

    @property
    def semantics_buffer(self) -> Dict[str, Any]:
        return self._semantics_buffer

    @semantics_buffer.setter
    def semantics_buffer(self, value: Mapping[str, Any]) -> None:
        self._semantics_buffer = _normalize_semantics_buffer(value)
        self._rdflib_graph = None

    def add_namespace(self, prefix: str, iri: str) -> None:
        self.namespaces[str(prefix)] = str(iri)
        if self._rdflib_graph is not None:
            self._rdflib_graph.bind(prefix, Namespace(iri))

    def _socket_uri(self, ref: _SocketRef) -> URIRef:
        base = f"urn:node-graph:{self.graph_uuid or 'graph'}:"
        suffix = f"{ref.task_name}:{ref.kind}:{ref.socket_path}"
        return URIRef(base + suffix.replace(" ", "_"))

    def _bind_namespaces(self, graph: RDFGraph) -> None:
        for prefix, iri in self.namespaces.items():
            try:
                graph.bind(prefix, Namespace(iri))
            except Exception:
                continue

    def _to_uri(self, term: str) -> URIRef:
        if "://" in term:
            return URIRef(term)
        if ":" in term:
            prefix, local = term.split(":", 1)
            if prefix in self.namespaces:
                return URIRef(self.namespaces[prefix] + local)
        return URIRef(term)

    def _literal_or_ref(self, value: Any) -> Union[URIRef, Literal]:
        if isinstance(value, _SocketRef):
            return self._socket_uri(value)
        if isinstance(value, str):
            if "://" in value or (
                ":" in value and value.split(":", 1)[0] in self.namespaces
            ):
                return self._to_uri(value)
            return Literal(value)
        if isinstance(value, (int, float, bool)):
            return Literal(value)
        if isinstance(value, dict):
            return Literal(json.dumps(value, default=str))
        if isinstance(value, (list, tuple, set)):
            return Literal(json.dumps(list(value), default=str))
        return Literal(value)

    def _annotation_from(self, semantics: Any) -> Optional[SemanticsAnnotation]:
        if semantics is None:
            return None
        if isinstance(semantics, SemanticsAnnotation):
            return semantics
        return SemanticsAnnotation.from_raw(semantics)

    def _add_payload(self, graph: RDFGraph, payload: SemanticsPayload) -> None:
        if payload.subject is None:
            return
        subject = self._socket_uri(payload.subject)
        base_label = (
            payload.socket_label
            or f"{payload.subject.task_name}.{payload.subject.socket_path}"
        )
        graph.add((subject, RDFS.label, Literal(base_label)))

        annotation = self._annotation_from(payload.semantics)
        if annotation is None:
            return

        # Merge namespaces discovered in the annotation back into the graph bindings
        for prefix, iri in annotation.context.items():
            if prefix not in self.namespaces:
                self.add_namespace(prefix, iri)
        self._bind_namespaces(graph)

        if annotation.label:
            graph.add((subject, RDFS.label, Literal(annotation.label)))
        if annotation.iri:
            graph.add((subject, RDF.type, self._to_uri(annotation.iri)))
        for rdf_type in annotation.rdf_types:
            graph.add((subject, RDF.type, self._to_uri(rdf_type)))
        for predicate, value in annotation.attributes.items():
            graph.add(
                (subject, self._to_uri(str(predicate)), self._literal_or_ref(value))
            )
        for predicate, value in annotation.relations.items():
            node = self._literal_or_ref(value)
            graph.add((subject, self._to_uri(str(predicate)), node))

    def _add_relation(self, graph: RDFGraph, relation: SemanticsRelation) -> None:
        if relation.subject is None or not relation.predicate:
            return
        subject = self._socket_uri(relation.subject)
        predicate = self._to_uri(relation.predicate)
        for value in relation.values:
            graph.add((subject, predicate, self._literal_or_ref(value)))
        if relation.label:
            graph.add((subject, RDFS.label, Literal(relation.label)))
        if relation.context:
            for prefix, iri in relation.context.items():
                if prefix not in self.namespaces:
                    self.add_namespace(prefix, iri)

    def as_rdflib(self) -> RDFGraph:
        if self._rdflib_graph is not None:
            return self._rdflib_graph

        graph = RDFGraph()
        self._bind_namespaces(graph)

        for payload in self._semantics_buffer.get("payloads", []):
            if isinstance(payload, SemanticsPayload):
                self._add_payload(graph, payload)
        for relation in self._semantics_buffer.get("relations", []):
            if isinstance(relation, SemanticsRelation):
                self._add_relation(graph, relation)

        self._rdflib_graph = graph
        return self._rdflib_graph

    def build_from_graph(self, graph: Any) -> RDFGraph:
        self.graph_uuid = getattr(graph, "uuid", self.graph_uuid)
        self.semantics_buffer = getattr(graph, "semantics_buffer", _default_buffer())
        return self.as_rdflib()

    def to_graphviz(self) -> "Digraph":
        if Digraph is None:  # pragma: no cover - import guarded
            raise RuntimeError(
                "graphviz is not installed; please `pip install graphviz`."
            )

        rdf = self.as_rdflib()
        dot = Digraph(name="KnowledgeGraph")
        node_ids: Dict[Any, str] = {}

        def _label(term: Any) -> str:
            try:
                return rdf.namespace_manager.normalizeUri(term)
            except Exception:
                return str(term)

        def _node_id(term: Any) -> str:
            if term not in node_ids:
                node_ids[term] = f"n{len(node_ids)}"
            return node_ids[term]

        for subj, pred, obj in rdf:
            s_id = _node_id(subj)
            o_id = _node_id(obj)
            dot.node(s_id, _label(subj))
            dot.node(o_id, _label(obj))
            dot.edge(s_id, o_id, label=_label(pred))
        return dot

    def to_graphviz_svg(self) -> str:
        graph = self.to_graphviz()
        return graph.pipe(format="svg").decode("utf-8")

    def _repr_svg_(self) -> Optional[str]:  # pragma: no cover - exercised in notebooks
        try:
            return self.to_graphviz_svg()
        except RuntimeError:
            return None

    def _zoomable_html_fragment(
        self,
        *,
        container_id: str,
        inner_id: str,
        svg: str,
        zoom_in_id: str,
        zoom_out_id: str,
        reset_id: str,
        fullscreen_id: str,
        container_class: str = "",
        container_style: str = "",
        viewport_class: str = "",
        viewport_style: str = "",
        controls_class: str = "",
    ) -> str:
        """Reusable HTML/JS snippet that wires zoom/fullscreen controls to a graph SVG."""
        container_class_attr = f' class="{container_class}"' if container_class else ""
        container_style_attr = f' style="{container_style}"' if container_style else ""
        viewport_class_attr = f' class="{viewport_class}"' if viewport_class else ""
        viewport_style_attr = f' style="{viewport_style}"' if viewport_style else ""
        controls_class_attr = f' class="{controls_class}"' if controls_class else ""

        return "\n".join(
            [
                f'<div id="{container_id}"{container_class_attr}{container_style_attr}>',
                f"  <div{controls_class_attr}>",
                f'    <button id="{zoom_in_id}" title="Zoom in">+</button>',
                f'    <button id="{zoom_out_id}" title="Zoom out">-</button>',
                f'    <button id="{reset_id}" title="Reset zoom">reset</button>',
                f'    <button id="{fullscreen_id}" title="Fullscreen">fullscreen</button>',
                "  </div>",
                f'  <div id="{inner_id}"{viewport_class_attr}{viewport_style_attr}>{svg}</div>',
                "</div>",
                "<script>",
                "  (function() {",
                f"    const container = document.getElementById('{container_id}');",
                f"    const viewport = document.getElementById('{inner_id}');",
                f"    const btnIn = document.getElementById('{zoom_in_id}');",
                f"    const btnOut = document.getElementById('{zoom_out_id}');",
                f"    const btnReset = document.getElementById('{reset_id}');",
                f"    const btnFs = document.getElementById('{fullscreen_id}');",
                "    let kgScale = 1;",
                "    const clamp = (val) => Math.min(4, Math.max(0.25, val));",
                "    const apply = () => { viewport.style.transform = `scale(${kgScale})`; };",
                "    const setScale = (val) => { kgScale = clamp(val); apply(); };",
                "    const onWheel = (ev) => {",
                "      if (!ev.ctrlKey) return;",
                "      ev.preventDefault();",
                "      const factor = ev.deltaY < 0 ? 1.1 : 1/1.1;",
                "      const prev = kgScale;",
                "      setScale(kgScale * factor);",
                "      const rect = viewport.getBoundingClientRect();",
                "      const offsetX = ev.clientX - rect.left;",
                "      const offsetY = ev.clientY - rect.top;",
                "      const ratio = kgScale / prev;",
                "      container.scrollLeft = offsetX * (ratio - 1) + container.scrollLeft;",
                "      container.scrollTop = offsetY * (ratio - 1) + container.scrollTop;",
                "    };",
                "    container.addEventListener('wheel', onWheel, { passive: false });",
                "    btnIn.onclick = () => setScale(kgScale * 1.2);",
                "    btnOut.onclick = () => setScale(kgScale / 1.2);",
                "    btnReset.onclick = () => setScale(1);",
                "    btnFs.onclick = () => {",
                "      if (!document.fullscreenElement) { container.requestFullscreen?.(); }",
                "      else { document.exitFullscreen?.(); }",
                "    };",
                "    setScale(1);",
                "  }());",
                "</script>",
            ]
        )

    def _repr_html_(self) -> Optional[str]:  # pragma: no cover - exercised in notebooks
        svg = self._repr_svg_()
        if svg is None:
            return None
        container_id = f"kg-{self.graph_uuid or uuid4()}"
        inner_id = f"{container_id}-inner"
        zoom_in_id = f"{container_id}-zin"
        zoom_out_id = f"{container_id}-zout"
        reset_id = f"{container_id}-reset"
        fullscreen_id = f"{container_id}-fs"
        fragment = self._zoomable_html_fragment(
            container_id=container_id,
            inner_id=inner_id,
            svg=svg,
            zoom_in_id=zoom_in_id,
            zoom_out_id=zoom_out_id,
            reset_id=reset_id,
            fullscreen_id=fullscreen_id,
            container_class="node-graph-knowledge-graph",
            container_style="overflow:auto; position:relative;",
            viewport_style="transform-origin: top left; display:inline-block;",
            controls_class="node-graph-kg-controls",
        )
        return "\n".join(
            [
                "<style>",
                f"  #{container_id}, #{container_id} svg {{ background: #ffffff; }}",
                f"  #{container_id}:fullscreen {{ background: #ffffff; }}",
                "</style>",
                fragment,
            ]
        )

    def to_html(self, title: Optional[str] = None) -> str:
        """Return an HTML document embedding the rendered knowledge graph with basic zoom/fullscreen controls."""
        svg = self.to_graphviz_svg()
        page_title = title or f"{self.graph_uuid or 'Graph'} knowledge graph"
        container_id = f"kg-{self.graph_uuid or uuid4()}"
        inner_id = f"{container_id}-inner"
        zoom_in_id = f"{container_id}-zin"
        zoom_out_id = f"{container_id}-zout"
        reset_id = f"{container_id}-reset"
        fullscreen_id = f"{container_id}-fs"
        fragment = self._zoomable_html_fragment(
            container_id=container_id,
            inner_id=inner_id,
            svg=svg,
            zoom_in_id=zoom_in_id,
            zoom_out_id=zoom_out_id,
            reset_id=reset_id,
            fullscreen_id=fullscreen_id,
            container_class="kg-container",
            container_style="overflow:auto;",
            viewport_class="kg-viewport",
            controls_class="kg-controls",
        )
        return """<!DOCTYPE html>\n""" + "\n".join(
            [
                '<html lang="en">',
                "  <head>",
                '    <meta charset="utf-8" />',
                f"    <title>{page_title}</title>",
                "    <style>",
                "      body {",
                "        font-family: Helvetica, Arial, sans-serif;",
                "        background-color: #f9f9fb;",
                "        margin: 0;",
                "        padding: 1.5rem;",
                "        color: #212121;",
                "      }",
                "      .container {",
                "        background-color: #ffffff;",
                "        padding: 1.5rem;",
                "        border-radius: 12px;",
                "        box-shadow: 0 10px 25px rgba(0, 0, 0, 0.05);",
                "        overflow: auto;",
                "        position: relative;",
                "        min-height: 60vh;",
                "      }",
                "      .kg-container { background: #ffffff; }",
                "      .kg-container:fullscreen { background: #ffffff; }",
                "      .kg-container svg { background: #ffffff; }",
                "      h1 {",
                "        font-size: 1.5rem;",
                "        margin-top: 0;",
                "        margin-bottom: 1rem;",
                "      }",
                "      svg {",
                "        height: auto;",
                "      }",
                "      .kg-controls {",
                "        display: flex;",
                "        gap: 0.5rem;",
                "        margin-bottom: 0.75rem;",
                "        flex-wrap: wrap;",
                "      }",
                "      .kg-controls button {",
                "        padding: 0.35rem 0.75rem;",
                "        border-radius: 6px;",
                "        border: 1px solid #e0e0e0;",
                "        background: #fafafa;",
                "        cursor: pointer;",
                "      }",
                "      .kg-controls button:hover {",
                "        background: #f1f1f1;",
                "      }",
                "      .kg-viewport {",
                "        transform-origin: top left;",
                "        display: inline-block;",
                "      }",
                "    </style>",
                "  </head>",
                "  <body>",
                '    <div class="container">',
                f"      <h1>{page_title}</h1>",
                f"      {fragment}",
                "    </div>",
                "  </body>",
                "</html>",
            ]
        )

    def save_html(self, path: str, title: Optional[str] = None) -> str:
        html = self.to_html(title=title)
        path_obj = Path(path)
        path_obj.parent.mkdir(parents=True, exist_ok=True)
        path_obj.write_text(html, encoding="utf-8")
        return str(path_obj)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "graph_uuid": self.graph_uuid,
            "namespaces": dict(self.namespaces),
            "semantics_buffer": serialize_semantics_buffer(self._semantics_buffer),
        }

    @classmethod
    def from_dict(
        cls,
        payload: Optional[Mapping[str, Any]],
        *,
        graph_uuid: Optional[str] = None,
    ) -> "KnowledgeGraph":
        if payload is None:
            return cls(graph_uuid=graph_uuid)
        namespaces = payload.get("namespaces") or namespace_registry()
        buffer = payload.get("semantics_buffer") or _default_buffer()
        graph_uuid = payload.get("graph_uuid") or graph_uuid
        return cls(
            graph_uuid=graph_uuid,
            semantics_buffer=buffer,
            namespaces=namespaces,
        )

    def copy(self, *, graph_uuid: Optional[str] = None) -> "KnowledgeGraph":
        return KnowledgeGraph(
            graph_uuid=graph_uuid or self.graph_uuid,
            semantics_buffer=serialize_semantics_buffer(self._semantics_buffer),
            namespaces=dict(self.namespaces),
        )


__all__ = ["KnowledgeGraph"]
