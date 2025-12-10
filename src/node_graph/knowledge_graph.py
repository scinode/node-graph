from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4
from typing import Any, Dict, Mapping, Optional, Union, Tuple, List

from rdflib import Graph as RDFGraph
from rdflib import Literal, Namespace, URIRef
from rdflib.namespace import RDFS

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


class KnowledgeGraph:
    """Light-weight container for semantics-backed knowledge graphs."""

    def __init__(
        self,
        *,
        graph_uuid: Optional[str] = None,
        namespaces: Optional[Mapping[str, str]] = None,
        graph: Any = None,
    ) -> None:
        """Initialize a KnowledgeGraph with optional identifiers and namespace bindings."""
        self.graph_uuid = graph_uuid
        self.namespaces: Dict[str, str] = dict(namespaces or namespace_registry())
        self._rdflib_graph: Optional[RDFGraph] = None
        self._payload: Dict[str, Any] = {}
        self._dirty: bool = True
        self._graph: Any = graph
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
        for prefix, iri in annotation.context.items():
            if prefix not in self.namespaces:
                self.add_namespace(prefix, iri)
        self._emit_label(sid, payload.subject, annotation.label, payload.socket_label)
        self._emit_annotation_triples(sid, annotation)
        self._dirty = False
        self._rdflib_graph = None

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
        for value in relation.values:
            obj = self._object_value(value)
            self._add_link(sid, relation.predicate, obj)
        self._dirty = False
        self._rdflib_graph = None

    def add_namespace(self, prefix: str, iri: str) -> None:
        """Register a namespace prefix/IRI pair on the knowledge graph instance."""
        self.namespaces[str(prefix)] = str(iri)
        if self._rdflib_graph is not None:
            self._rdflib_graph.bind(prefix, Namespace(iri))

    def _socket_uri(self, ref: _SocketRef) -> URIRef:
        """Return a deterministic URI for a socket reference."""
        base = f"urn:node-graph:{self.graph_uuid or 'graph'}:"
        suffix = f"{ref.task_name}:{ref.kind}:{ref.socket_path}"
        return URIRef(base + suffix.replace(" ", "_"))

    def _bind_namespaces(self, graph: RDFGraph) -> None:
        """Bind all known namespaces to the given rdflib graph."""
        for prefix, iri in self.namespaces.items():
            try:
                graph.bind(prefix, Namespace(iri))
            except Exception:
                continue

    def _socket_name(self, task_name: str, direction: str, socket_path: str) -> str:
        """Compose a stable socket identifier."""
        socket_part = socket_path or "socket"
        return f"{task_name}.{direction}.{socket_part}"

    def _ensure_socket(
        self, ref: _SocketRef, socket_label: Optional[str] = None
    ) -> str:
        """Return a socket id for ``ref``, creating an entity if missing."""

        socket_id = getattr(
            ref,
            "_full_name_with_task",
            self._socket_name(ref.task_name, ref.kind, ref.socket_path),
        )
        meta = self.entities.get(socket_id)
        if meta is None:
            meta = {
                "task": ref.task_name,
                "direction": ref.kind,
                "port": ref.socket_path,
                "canonical": socket_id,
            }
            if socket_label:
                meta["label"] = socket_label
            self.entities[socket_id] = meta
        elif socket_label and not meta.get("label"):
            meta["label"] = socket_label
        return socket_id

    def _add_link(self, subject: str, predicate: str, obj: Any) -> None:
        """Append a triple-like link if it has not been recorded yet."""
        triple = [subject, predicate, obj]
        if triple not in self.links:
            self.links.append(triple)

    def _ensure_sockets_in_value(self, value: Any) -> None:
        """Ensure nested socket references are materialized in ``entities``."""
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
        """Add rdfs:label triples for a socket with sensible defaults."""
        default_label = f"{ref.task_name}.{ref.socket_path or 'socket'}"
        label_value = socket_label or annotation_label or default_label
        self._add_link(socket_id, "rdfs:label", label_value)
        if annotation_label and annotation_label != label_value:
            self._add_link(socket_id, "rdfs:label", annotation_label)

    def _emit_annotation_triples(
        self,
        socket_id: str,
        annotation: SemanticsAnnotation,
    ) -> None:
        """Emit triples for a semantics annotation onto the internal link list."""
        for rdf_type in annotation.rdf_types:
            self._add_link(socket_id, "rdf:type", rdf_type)
        if annotation.iri:
            self._add_link(socket_id, "rdf:type", annotation.iri)
        for predicate, value in annotation.attributes.items():
            if isinstance(value, (list, tuple, set)):
                for item in value:
                    self._add_link(socket_id, str(predicate), self._object_value(item))
                continue
            self._add_link(socket_id, str(predicate), self._object_value(value))
        for predicate, value in annotation.relations.items():
            if isinstance(value, (list, tuple, set)):
                for item in value:
                    self._add_link(socket_id, str(predicate), self._object_value(item))
                continue
            self._add_link(socket_id, str(predicate), self._object_value(value))

    def _rebuild_payload_from_entities(self) -> Dict[str, Any]:
        """Reconstruct a payload dictionary from the current entities/links."""
        sockets: Dict[str, Dict[str, Any]] = {}
        for sid, meta in self.entities.items():
            meta_copy = dict(meta)
            meta_copy.pop("canonical", None)
            sockets[sid] = meta_copy
        context = dict(self.namespaces)
        context.setdefault("rdf", "http://www.w3.org/1999/02/22-rdf-syntax-ns#")
        context.setdefault("rdfs", "http://www.w3.org/2000/01/rdf-schema#")
        payload = {
            "context": context,
            "sockets": sockets,
            "triples": list(self.links),
        }
        self._payload = payload
        return payload

    def _to_uri(self, term: str) -> URIRef:
        """Coerce a CURIE or absolute string into an rdflib URIRef."""
        if "://" in term:
            return URIRef(term)
        if ":" in term:
            prefix, local = term.split(":", 1)
            if prefix in self.namespaces:
                return URIRef(self.namespaces[prefix] + local)
        return URIRef(term)

    def _literal_or_ref(self, value: Any) -> Union[URIRef, Literal]:
        """Convert a Python value into an rdflib Literal or URIRef."""
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
        """Normalize raw semantics payloads into SemanticsAnnotation."""
        if semantics is None:
            return None
        if isinstance(semantics, SemanticsAnnotation):
            return semantics
        return SemanticsAnnotation.from_raw(semantics)

    def as_rdflib(self) -> RDFGraph:
        """Return the knowledge graph as an rdflib Graph, rebuilding caches as needed."""
        self.update()
        payload = self._rebuild_payload_from_entities()
        graph = RDFGraph()
        context = payload.get("context") or {}
        for prefix, iri in context.items():
            self.add_namespace(prefix, iri)
        self._bind_namespaces(graph)

        sockets = payload.get("sockets") or {}
        triples = payload.get("triples") or []

        def _socket_uri_by_id(sid: str) -> URIRef:
            if isinstance(sid, str) and sid.startswith("ng://"):
                return URIRef(sid)
            return self._to_uri(str(sid))

        for sid, meta in sockets.items():
            uri = _socket_uri_by_id(sid)
            label = meta.get("label")
            if label:
                graph.add((uri, RDFS.label, Literal(label)))

        for subj, pred, obj in triples:
            subj_uri = _socket_uri_by_id(str(subj))
            pred_uri = self._to_uri(str(pred))
            if isinstance(obj, str) and obj in sockets:
                obj_val: Union[URIRef, Literal] = _socket_uri_by_id(obj)
            else:
                obj_val = self._literal_or_ref(obj)
            graph.add((subj_uri, pred_uri, obj_val))

        self._rdflib_graph = graph
        return self._rdflib_graph

    def to_graphviz(self) -> "Digraph":
        """Render the knowledge graph into a Graphviz Digraph."""
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
        """Return an SVG serialization of the knowledge graph via graphviz."""
        graph = self.to_graphviz()
        return graph.pipe(format="svg").decode("utf-8")

    def _repr_svg_(self) -> Optional[str]:
        """IPython/Jupyter SVG repr hook."""
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
        """HTML repr hook that reuses the graphviz SVG with controls."""
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
        """Serialize the HTML view to ``path`` and return the resolved path."""
        html = self.to_html(title=title)
        path_obj = Path(path)
        path_obj.parent.mkdir(parents=True, exist_ok=True)
        path_obj.write_text(html, encoding="utf-8")
        return str(path_obj)

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-friendly snapshot of namespaces, sockets, and triples."""
        self.update()
        return {
            "namespaces": dict(self.namespaces),
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
        """Construct a KnowledgeGraph from a serialized payload."""
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
        """Return a shallow copy that preserves current state and identifiers."""
        kg = KnowledgeGraph(
            graph_uuid=graph_uuid or self.graph_uuid,
            namespaces=dict(self.namespaces),
            graph=self._graph,
        )
        kg._payload = dict(self._payload) if isinstance(self._payload, dict) else {}
        kg._dirty = self._dirty
        kg.entities = {sid: dict(meta) for sid, meta in self.entities.items()}
        kg.links = [list(triple) for triple in self.links]
        return kg

    def _merge_annotation(
        self,
        base: Optional[SemanticsAnnotation],
        extra: Optional[SemanticsAnnotation],
    ) -> Optional[SemanticsAnnotation]:
        """Merge two annotations, preferring non-empty fields from ``extra``."""
        if base is None:
            return extra
        if extra is None:
            return base
        return base.merge(extra)

    def _flatten_semantics_tree(
        self, tree: Optional[Any], *, task_name: str, direction: str
    ) -> Dict[Tuple[str, str, str], SemanticsAnnotation]:
        """Flatten nested semantics trees keyed by task/direction/socket path."""
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
        """Collect semantics annotations from a graph's tasks into a mapping."""
        entries: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
        graph = graph or self._graph
        if graph is not None:
            for task in graph.tasks:
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
        """Build a merged namespace context from collected semantics."""
        context: Dict[str, str] = {
            "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
            "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
        }
        for annotation in (entry.get("annotation") for entry in entries.values()):
            if annotation is None:
                continue
            context.update(annotation.context)
        return context

    def _object_value(self, value: Any) -> Any:
        """Normalize attribute/relation payloads into serialisable objects."""
        if isinstance(value, _SocketRef):
            socket_id = getattr(
                value,
                "_full_name_with_task",
                self._socket_name(value.task_name, value.kind, value.socket_path),
            )
            return socket_id
        if isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, dict):
            return json.dumps(value, default=str)
        if isinstance(value, (list, tuple, set)):
            return json.dumps(list(value), default=str)
        return repr(value)

    def _triples_from_entries(
        self, entries: Dict[Tuple[str, str, str], Dict[str, Any]]
    ) -> List[List[Any]]:
        """Build triples from collected semantics entries, deduplicating repeats."""
        triples: List[List[Any]] = []
        seen: set[Tuple[Any, Any, Any]] = set()

        def _emit(subject: str, predicate: str, value: Any) -> None:
            if isinstance(value, (list, tuple, set)):
                for item in value:
                    _emit(subject, predicate, item)
                return
            sig = (subject, predicate, self._object_value(value))
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
            subject_id = self._socket_name(task_name, direction, socket_path)
            subject = subject_id
            if subject is None:
                continue
            default_label = f"{task_name}.{direction}.{socket_path or 'socket'}"
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

    def update(self) -> Dict[str, Any]:
        """
        Refresh entities/links from the current graph structure.
        """

        graph = self._graph
        entries = self._collect_socket_semantics(graph)
        if not entries:
            return
        self.namespaces.update(self._merge_context(entries))
        new_sockets: Dict[str, Dict[str, Any]] = {}
        for key, entry in sorted(entries.items(), key=lambda item: item[0]):
            task_name, direction, socket_path = key
            socket_id = self._socket_name(task_name, direction, socket_path)
            socket_meta: Dict[str, Any] = {
                "task": task_name,
                "direction": direction,
                "port": socket_path,
                "canonical": socket_id,
            }
            label = entry.get("socket_label")
            annotation = entry.get("annotation")
            if not label and isinstance(annotation, SemanticsAnnotation):
                label = annotation.label
            if label:
                socket_meta["label"] = label
            new_sockets[socket_id] = socket_meta

        new_triples = self._triples_from_entries(entries)

        entities: Dict[str, Dict[str, Any]] = dict(self.entities)
        for sid, meta in new_sockets.items():
            if sid not in entities:
                entities[sid] = dict(meta)

        links: List[List[Any]] = list(self.links)
        seen = {tuple(link) for link in links}
        for triple in new_triples:
            sig = tuple(triple)
            if sig in seen:
                continue
            seen.add(sig)
            links.append(triple)

        self.entities = entities
        self.links = links
        self._payload = {
            "context": dict(self.namespaces),
            "sockets": entities,
            "triples": links,
        }


__all__ = ["KnowledgeGraph"]
