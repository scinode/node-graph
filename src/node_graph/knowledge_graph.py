from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4
from typing import Any, Dict, Mapping, Optional, Union, Tuple, Iterable, List

from rdflib import Graph as RDFGraph
from rdflib import Literal, Namespace, URIRef
from rdflib.namespace import RDF, RDFS

from node_graph.semantics import (
    SemanticsAnnotation,
    SemanticsPayload,
    SemanticsRelation,
    _SocketRef,
    namespace_registry,
    TaskSemantics,
)

try:
    from graphviz import Digraph
except Exception:
    Digraph = None


def _canonical_socket_id(task_name: str, direction: str, socket_path: str) -> str:
    socket_part = socket_path or "socket"
    return f"ng://{task_name}/{direction}/{socket_part}"


class KnowledgeGraph:
    """Light-weight container for semantics-backed knowledge graphs."""

    def __init__(
        self,
        *,
        graph_uuid: Optional[str] = None,
        namespaces: Optional[Mapping[str, str]] = None,
        graph: Any = None,
    ) -> None:
        self.graph_uuid = graph_uuid
        self.namespaces: Dict[str, str] = dict(namespaces or namespace_registry())
        self._rdflib_graph: Optional[RDFGraph] = None
        self._payload: Dict[str, Any] = {}
        self._dirty: bool = True
        self._graph: Any = graph
        self._graph_version: Optional[int] = (
            getattr(graph, "_version", None) if graph else None
        )
        self.entities: Dict[str, Dict[str, Any]] = {}
        self.links: List[List[Any]] = []

    def add_payload(self, payload: SemanticsPayload) -> None:
        """Record a semantics payload directly into entities/links."""

        if payload.subject is None:
            return
        sid = self._ensure_socket(payload.subject, socket_label=payload.socket_label)
        annotation = self._annotation_from(payload.semantics)
        if annotation is None:
            return
        for value in list(annotation.attributes.values()) + list(
            annotation.relations.values()
        ):
            self._ensure_sockets_in_value(value)
        socket_index = self._socket_index()
        for prefix, iri in annotation.context.items():
            if prefix not in self.namespaces:
                self.add_namespace(prefix, iri)
        self._emit_label(sid, payload.subject, annotation.label, payload.socket_label)
        self._emit_annotation_triples(sid, annotation, socket_index)
        self._dirty = False
        self._rdflib_graph = None
        self._rebuild_payload_from_entities()

    def add_relation(self, relation: SemanticsRelation) -> None:
        """Record a semantics relation directly into entities/links."""

        if relation.subject is None or not relation.predicate:
            return
        sid = self._ensure_socket(relation.subject, socket_label=relation.socket_label)
        for value in relation.values:
            self._ensure_sockets_in_value(value)
        if relation.context:
            for prefix, iri in relation.context.items():
                if prefix not in self.namespaces:
                    self.add_namespace(prefix, iri)
        if relation.label:
            self._emit_label(
                sid, relation.subject, relation.label, relation.socket_label
            )
        socket_index = self._socket_index()
        for value in relation.values:
            obj = self._object_value(value, socket_index)
            self._add_link(sid, relation.predicate, obj)
        self._dirty = False
        self._rdflib_graph = None
        self._rebuild_payload_from_entities()

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

    def _ensure_current(self) -> Dict[str, Any]:
        """
        Ensure entities/links are up to date with the backing graph.

        Rebuilds whenever marked dirty or when the DAG structure hash changes.
        """

        current_version = getattr(self._graph, "_version", None)
        if self._dirty or (
            current_version is not None and current_version != self._graph_version
        ):
            self.update(self._graph)
        return self._payload

    def _materialize(self) -> Dict[str, Any]:
        return self._ensure_current()

    def _socket_index(self) -> Dict[str, str]:
        index: Dict[str, str] = {}
        for sid, meta in self.entities.items():
            canonical = meta.get("canonical")
            if canonical:
                index[str(canonical)] = sid
        return index

    def _ensure_socket(
        self, ref: _SocketRef, socket_label: Optional[str] = None
    ) -> str:
        """Return a compact socket id for ``ref``, creating an entity if missing."""

        canonical = _canonical_socket_id(ref.task_name, ref.kind, ref.socket_path)
        socket_id = self._socket_index().get(canonical)
        if socket_id is None:
            socket_id = f"s{len(self.entities) + 1}"
            meta: Dict[str, Any] = {
                "task": ref.task_name,
                "direction": ref.kind,
                "port": ref.socket_path,
                "canonical": canonical,
            }
            if socket_label:
                meta["label"] = socket_label
            self.entities[socket_id] = meta
        else:
            meta = self.entities[socket_id]
            if socket_label and not meta.get("label"):
                meta["label"] = socket_label
        return socket_id

    def _add_link(self, subject: str, predicate: str, obj: Any) -> None:
        triple = [subject, predicate, obj]
        if triple not in self.links:
            self.links.append(triple)

    def _ensure_sockets_in_value(self, value: Any) -> None:
        if isinstance(value, _SocketRef):
            self._ensure_socket(value)
            return
        if isinstance(value, (list, tuple, set)):
            for item in value:
                self._ensure_sockets_in_value(item)

    def _emit_label(
        self,
        socket_id: str,
        ref: _SocketRef,
        annotation_label: Optional[str],
        socket_label: Optional[str],
    ) -> None:
        default_label = f"{ref.task_name}.{ref.socket_path or 'socket'}"
        label_value = socket_label or annotation_label or default_label
        self._add_link(socket_id, "rdfs:label", label_value)
        if annotation_label and annotation_label != label_value:
            self._add_link(socket_id, "rdfs:label", annotation_label)

    def _emit_annotation_triples(
        self,
        socket_id: str,
        annotation: SemanticsAnnotation,
        socket_index: Dict[str, str],
    ) -> None:
        for rdf_type in annotation.rdf_types:
            self._add_link(socket_id, "rdf:type", rdf_type)
        if annotation.iri:
            self._add_link(socket_id, "rdf:type", annotation.iri)
        for predicate, value in annotation.attributes.items():
            self._add_link(
                socket_id, str(predicate), self._object_value(value, socket_index)
            )
        for predicate, value in annotation.relations.items():
            self._add_link(
                socket_id, str(predicate), self._object_value(value, socket_index)
            )

    def _rebuild_payload_from_entities(self) -> Dict[str, Any]:
        socket_index: Dict[str, str] = self._socket_index()
        sockets: Dict[str, Dict[str, Any]] = {}
        for sid, meta in self.entities.items():
            meta_copy = dict(meta)
            meta_copy.pop("canonical", None)
            sockets[sid] = meta_copy
        context = dict(self.namespaces)
        context.setdefault("rdf", "http://www.w3.org/1999/02/22-rdf-syntax-ns#")
        context.setdefault("rdfs", "http://www.w3.org/2000/01/rdf-schema#")
        self._graph_version = getattr(self._graph, "_version", None)
        payload = {
            "context": context,
            "socket_index": socket_index,
            "sockets": sockets,
            "triples": list(self.links),
        }
        self._payload = payload
        return payload

    def _refresh_from_graph(self, graph: Optional[Any] = None) -> None:
        """Populate entities/links from the backing task graph if empty."""

        graph = graph or self._graph
        current_version = (
            getattr(graph, "_version", None) if graph is not None else None
        )
        if (
            self.entities
            and self.links
            and (self._graph_version is None or self._graph_version == current_version)
        ):
            self._dirty = False
            return
        if graph is None:
            self.entities = {}
            self.links = []
            self._payload = {}
            self._dirty = False
            return
        entries = self._collect_socket_semantics(graph)
        if not entries:
            self.entities = {}
            self.links = []
            self._payload = {}
            self._dirty = False
            return
        context = self._merge_context(entries)
        socket_index, sockets = self._build_socket_index(entries)
        triples = self._triples_from_entries(entries, socket_index)
        self.entities = dict(sockets)
        self.links = list(triples)
        self._graph_version = current_version
        self._payload = {
            "context": context,
            "socket_index": socket_index,
            "sockets": sockets,
            "triples": triples,
        }
        self._dirty = False

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

        payload = self._materialize()
        graph = RDFGraph()
        context = payload.get("context") or {}
        for prefix, iri in context.items():
            self.add_namespace(prefix, iri)
        self._bind_namespaces(graph)

        sockets = payload.get("sockets") or {}
        triples = payload.get("triples") or []
        socket_index = payload.get("socket_index") or {}
        inverse_index = {v: k for k, v in socket_index.items()}

        def _socket_uri_by_id(sid: str) -> URIRef:
            canonical = inverse_index.get(sid, sid)
            if isinstance(canonical, str) and canonical.startswith("ng://"):
                return URIRef(canonical)
            return self._to_uri(str(canonical))

        for sid, meta in sockets.items():
            uri = _socket_uri_by_id(sid)
            label = meta.get("label")
            if label:
                graph.add((uri, RDFS.label, Literal(label)))

        for subj, pred, obj in triples:
            subj_uri = _socket_uri_by_id(str(subj))
            pred_uri = self._to_uri(str(pred))
            if isinstance(obj, str) and (obj in sockets or obj in inverse_index):
                obj_val: Union[URIRef, Literal] = _socket_uri_by_id(obj)
            else:
                obj_val = self._literal_or_ref(obj)
            graph.add((subj_uri, pred_uri, obj_val))

        self._rdflib_graph = graph
        return self._rdflib_graph

    def build_from_graph(self, graph: Any) -> RDFGraph:
        self.graph_uuid = getattr(graph, "uuid", self.graph_uuid)
        self._graph = graph
        self._dirty = True
        self._rdflib_graph = None
        self._materialize()
        return self.as_rdflib()

    def to_graphviz(self) -> "Digraph":
        self._ensure_current()
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
        self.update(self._graph)
        return {
            "graph_uuid": self.graph_uuid,
            "namespaces": dict(self.namespaces),
            "socket_index": self._payload.get("socket_index"),
            "sockets": {sid: dict(meta) for sid, meta in self.entities.items()},
            "triples": list(self.links),
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
        graph_uuid = payload.get("graph_uuid") or graph_uuid
        kg = cls(graph_uuid=graph_uuid, namespaces=namespaces)
        sockets = payload.get("sockets") or {}
        triples = payload.get("triples") or []
        if sockets or triples:
            kg.entities = {sid: dict(meta) for sid, meta in sockets.items()}
            kg.links = [list(t) for t in triples]
            kg._payload = {
                "dag_id": payload.get("dag_id") or "",
                "context": dict(namespaces),
                "socket_index": payload.get("socket_index") or kg._socket_index(),
                "sockets": {
                    sid: {k: v for k, v in meta.items() if k != "canonical"}
                    for sid, meta in kg.entities.items()
                },
                "triples": list(kg.links),
            }
            kg._dirty = False
        else:
            semantics = payload.get("semantics")
            if isinstance(semantics, dict):
                kg._payload = semantics  # type: ignore[attr-defined]
                kg.entities = dict(semantics.get("sockets", {}))
                kg.links = list(semantics.get("triples", []))
                kg._dirty = False
        return kg

    def copy(self, *, graph_uuid: Optional[str] = None) -> "KnowledgeGraph":
        kg = KnowledgeGraph(
            graph_uuid=graph_uuid or self.graph_uuid,
            namespaces=dict(self.namespaces),
            graph=self._graph,
        )
        kg._payload = dict(self._payload) if isinstance(self._payload, dict) else {}
        kg._dirty = self._dirty
        kg._graph_version = self._graph_version
        kg.entities = {sid: dict(meta) for sid, meta in self.entities.items()}
        kg.links = [list(triple) for triple in self.links]
        return kg

    def _merge_annotation(
        self,
        base: Optional[SemanticsAnnotation],
        extra: Optional[SemanticsAnnotation],
    ) -> Optional[SemanticsAnnotation]:
        if base is None:
            return extra
        if extra is None:
            return base
        return base.merge(extra)

    def _merge_payload_annotations(
        self,
        target: Dict[Tuple[str, str, str], Dict[str, Any]],
        payloads: Iterable[SemanticsPayload],
    ) -> None:
        def _sanitize_semantics(raw: Any) -> Any:
            return raw

        for pending in payloads:
            if not isinstance(pending, SemanticsPayload):
                continue
            subject = pending.subject
            if not isinstance(subject, _SocketRef):
                continue
            key = (subject.task_name, subject.kind, subject.socket_path)
            entry = target.setdefault(key, {"annotation": None, "socket_label": None})
            extra = SemanticsAnnotation.from_raw(_sanitize_semantics(pending.semantics))
            if extra is None or extra.is_empty:
                continue
            entry["annotation"] = self._merge_annotation(entry.get("annotation"), extra)
            if pending.socket_label and not entry.get("socket_label"):
                entry["socket_label"] = pending.socket_label

    def _merge_relation_annotations(
        self,
        target: Dict[Tuple[str, str, str], Dict[str, Any]],
        relations: Iterable[SemanticsRelation],
    ) -> None:
        for relation in relations:
            if not isinstance(relation, SemanticsRelation):
                continue
            subject = relation.subject
            if not isinstance(subject, _SocketRef):
                continue
            key = (subject.task_name, subject.kind, subject.socket_path)
            entry = target.setdefault(key, {"annotation": None, "socket_label": None})
            payload = {
                "relations": {
                    relation.predicate: relation.values
                    if len(relation.values) > 1
                    else relation.values[0]
                }
            }
            if relation.label:
                payload["label"] = relation.label
            if relation.context:
                payload["context"] = dict(relation.context)
            extra = SemanticsAnnotation.from_raw(payload)
            entry["annotation"] = self._merge_annotation(entry.get("annotation"), extra)
            if relation.socket_label and not entry.get("socket_label"):
                entry["socket_label"] = relation.socket_label

    def _flatten_semantics_tree(
        self, tree: Optional[Any], *, task_name: str, direction: str
    ) -> Dict[Tuple[str, str, str], SemanticsAnnotation]:
        entries: Dict[Tuple[str, str, str], SemanticsAnnotation] = {}

        def _walk(node: Optional[Any], path: str) -> None:
            if node is None:
                return
            annotation = getattr(node, "annotation", None)
            if annotation and not annotation.is_empty:
                key = (task_name, direction, path or "")
                entries[key] = annotation
            for name, child in (getattr(node, "children", {}) or {}).items():
                child_path = f"{path}.{name}" if path else name
                _walk(child, child_path)
            dynamic = getattr(node, "dynamic", None)
            if dynamic:
                dynamic_path = f"{path}.*" if path else "*"
                _walk(dynamic, dynamic_path)

        _walk(tree, "")
        return entries

    def _collect_socket_semantics(
        self, graph: Optional[Any] = None
    ) -> Dict[Tuple[str, str, str], Dict[str, Any]]:
        entries: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
        graph = graph or self._graph
        if graph is not None:
            for task in getattr(graph, "tasks", []) or []:
                spec = getattr(task, "spec", None)
                if spec is None:
                    continue
                semantics = TaskSemantics.from_specs(spec.inputs, spec.outputs)
                if semantics is None:
                    continue
                for key, annotation in self._flatten_semantics_tree(
                    semantics.inputs,
                    task_name=getattr(task, "name", "<task>"),
                    direction="input",
                ).items():
                    entry = entries.setdefault(
                        key, {"annotation": None, "socket_label": None}
                    )
                    entry["annotation"] = self._merge_annotation(
                        entry.get("annotation"), annotation
                    )
                for key, annotation in self._flatten_semantics_tree(
                    semantics.outputs,
                    task_name=getattr(task, "name", "<task>"),
                    direction="output",
                ).items():
                    entry = entries.setdefault(
                        key, {"annotation": None, "socket_label": None}
                    )
                    entry["annotation"] = self._merge_annotation(
                        entry.get("annotation"), annotation
                    )

        return entries

    def _merge_context(
        self, entries: Dict[Tuple[str, str, str], Dict[str, Any]]
    ) -> Dict[str, str]:
        context: Dict[str, str] = {
            "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
            "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
        }
        for annotation in (entry.get("annotation") for entry in entries.values()):
            if annotation is None:
                continue
            context.update(annotation.context)
        return context

    def _build_socket_index(
        self, entries: Dict[Tuple[str, str, str], Dict[str, Any]]
    ) -> Tuple[Dict[str, str], Dict[str, Dict[str, Any]]]:
        """
        Return ``(socket_index, sockets)`` mapping canonical socket IDs to compact IDs.

        Each socket gets a compact id ``s{n}`` and carries basic metadata so
        triples can reference it consistently.
        """
        socket_index: Dict[str, str] = {}
        sockets: Dict[str, Dict[str, Any]] = {}
        for idx, (key, entry) in enumerate(
            sorted(entries.items(), key=lambda item: item[0]), start=1
        ):
            task_name, direction, socket_path = key
            compact = f"s{idx}"
            socket_meta: Dict[str, Any] = {
                "task": task_name,
                "direction": direction,
                "port": socket_path,
            }
            if entry.get("socket_label"):
                socket_meta["label"] = entry["socket_label"]
            annotation = entry.get("annotation")
            if socket_meta.get("label") is None and isinstance(
                annotation, SemanticsAnnotation
            ):
                if annotation.label:
                    socket_meta["label"] = annotation.label
            sockets[compact] = socket_meta
            canonical = _canonical_socket_id(task_name, direction, socket_path)
            socket_index[canonical] = compact
            sockets[compact]["canonical"] = canonical
        return socket_index, sockets

    def _object_value(self, value: Any, socket_index: Dict[str, str]) -> Any:
        if isinstance(value, _SocketRef):
            canonical = _canonical_socket_id(
                value.task_name, value.kind, value.socket_path
            )
            return socket_index.get(canonical, canonical)
        if isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, dict):
            return json.dumps(value, default=str)
        if isinstance(value, (list, tuple, set)):
            return json.dumps(list(value), default=str)
        return repr(value)

    def _triples_from_entries(
        self,
        entries: Dict[Tuple[str, str, str], Dict[str, Any]],
        socket_index: Dict[str, str],
    ) -> List[List[Any]]:
        triples: List[List[Any]] = []
        seen: set[Tuple[Any, Any, Any]] = set()

        def _emit(subject: str, predicate: str, value: Any) -> None:
            if isinstance(value, (list, tuple, set)):
                for item in value:
                    _emit(subject, predicate, item)
                return
            sig = (subject, predicate, self._object_value(value, socket_index))
            if sig in seen:
                return
            seen.add(sig)
            triples.append([subject, predicate, sig[2]])

        for (task_name, direction, socket_path), entry in sorted(
            entries.items(), key=lambda item: item[0]
        ):
            annotation: Optional[SemanticsAnnotation] = entry.get("annotation")
            if annotation is None or annotation.is_empty:
                continue
            canonical = _canonical_socket_id(task_name, direction, socket_path)
            subject = socket_index.get(canonical)
            if subject is None:
                continue
            default_label = f"{task_name}.{socket_path or 'socket'}"
            socket_label = entry.get("socket_label")
            label_value = socket_label or annotation.label or default_label
            _emit(subject, "rdfs:label", label_value)
            if annotation.label and annotation.label != label_value:
                _emit(subject, "rdfs:label", annotation.label)
            if annotation.iri:
                _emit(subject, "rdf:type", annotation.iri)
            for rdf_type in annotation.rdf_types:
                _emit(subject, "rdf:type", rdf_type)
            for predicate, value in annotation.attributes.items():
                _emit(subject, str(predicate), value)
            for predicate, value in annotation.relations.items():
                _emit(subject, str(predicate), value)
        return triples

    def update(self, graph: Optional[Any] = None) -> Dict[str, Any]:
        """
        Refresh entities/links from the current graph structure.
        """

        if graph is not None:
            self._graph = graph
        self._refresh_from_graph(self._graph)
        self._rdflib_graph = None
        return self._payload


__all__ = ["KnowledgeGraph"]
