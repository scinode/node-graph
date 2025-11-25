from __future__ import annotations

"""Semantics helpers shared between graph authoring and engine execution."""

from dataclasses import dataclass, field, asdict, is_dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from node_graph.socket import BaseSocket, TaggedValue
from node_graph.socket_spec import SocketSpec

SEMANTICS_BUFFER_ATTR = "semantics_buffer"


def _json_ready(value: Any) -> Any:
    """Convert semantics payloads into JSON-serialisable structures."""

    if is_dataclass(value):
        return _json_ready(asdict(value))
    if isinstance(value, Mapping):
        return {k: _json_ready(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_ready(v) for v in value]
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


def serialize_semantics_buffer(buffer: Any) -> Any:
    """Return a JSON-friendly representation of semantics buffer payloads."""

    return _json_ready(buffer)


@dataclass(frozen=True)
class SemanticsAnnotation:
    """Normalized ontology annotation extracted from socket metadata."""

    label: Optional[str] = None
    iri: Optional[str] = None
    rdf_types: Tuple[str, ...] = ()
    context: Dict[str, str] = field(default_factory=dict)
    attributes: Dict[str, Any] = field(default_factory=dict)
    relations: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_raw(
        cls, raw: Optional[Mapping[str, Any]]
    ) -> Optional["SemanticsAnnotation"]:
        if not raw:
            return None
        return cls(
            label=raw.get("label"),
            iri=raw.get("iri"),
            rdf_types=tuple(raw.get("rdf_types", []) or ()),
            context=dict(raw.get("context", {}) or {}),
            attributes=dict(raw.get("attributes", {}) or {}),
            relations=dict(raw.get("relations", {}) or {}),
        )

    @staticmethod
    def combine(
        annotations: Iterable[Optional["SemanticsAnnotation"]],
    ) -> Optional["SemanticsAnnotation"]:
        combined: Optional[SemanticsAnnotation] = None
        for annotation in annotations:
            if annotation is None or annotation.is_empty:
                continue
            if combined is None:
                combined = annotation
            else:
                combined = combined.merge(annotation)
        return combined

    @property
    def is_empty(self) -> bool:
        return (
            self.label is None
            and self.iri is None
            and not self.rdf_types
            and not self.context
            and not self.attributes
            and not self.relations
        )

    def merge(self, other: "SemanticsAnnotation") -> "SemanticsAnnotation":
        if other is None or other.is_empty:
            return self
        label = other.label if other.label is not None else self.label
        iri = other.iri if other.iri is not None else self.iri
        rdf_types: Tuple[str, ...]
        if self.rdf_types or other.rdf_types:
            rdf_types = tuple(dict.fromkeys((*self.rdf_types, *other.rdf_types)))
        else:
            rdf_types = ()
        context = dict(self.context)
        context.update(other.context)
        attributes = dict(self.attributes)
        attributes.update(other.attributes)
        relations = dict(self.relations)
        relations.update(other.relations)
        return SemanticsAnnotation(
            label=label,
            iri=iri,
            rdf_types=rdf_types,
            context=context,
            attributes=attributes,
            relations=relations,
        )

    def to_payload(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        if self.label is not None:
            payload["label"] = self.label
        if self.iri is not None:
            payload["iri"] = self.iri
        if self.rdf_types:
            payload["rdf_types"] = list(self.rdf_types)
        if self.context:
            payload["context"] = dict(self.context)
        if self.attributes:
            payload["attributes"] = dict(self.attributes)
        if self.relations:
            payload["relations"] = dict(self.relations)
        return payload

    def to_jsonld(self) -> Dict[str, Any]:
        jsonld: Dict[str, Any] = {}
        if self.context:
            jsonld["@context"] = dict(self.context)
        if self.iri is not None:
            jsonld["@id"] = self.iri
        if self.rdf_types:
            jsonld["@type"] = list(self.rdf_types)
        if self.label is not None:
            jsonld["label"] = self.label
        for predicate, value in self.attributes.items():
            jsonld[predicate] = value
        for predicate, value in self.relations.items():
            jsonld[predicate] = value
        return jsonld


@dataclass(frozen=True)
class SemanticsTree:
    """Tree representation mirroring the socket spec semantics."""

    annotation: Optional[SemanticsAnnotation] = None
    children: Dict[str, "SemanticsTree"] = field(default_factory=dict)
    dynamic: Optional["SemanticsTree"] = None

    @classmethod
    def from_spec(cls, spec: Optional[SocketSpec]) -> Optional["SemanticsTree"]:
        if spec is None:
            return None
        annotation = SemanticsAnnotation.from_raw(getattr(spec.meta, "semantics", None))
        children: Dict[str, SemanticsTree] = {}
        dynamic: Optional[SemanticsTree] = None
        if spec.is_namespace():
            for name, child in spec.fields.items():
                child_tree = cls.from_spec(child)
                if child_tree is not None:
                    children[name] = child_tree
            if spec.meta.dynamic:
                dynamic = cls.from_spec(spec.item)
        if annotation is None and not children and dynamic is None:
            return None
        return cls(annotation=annotation, children=children, dynamic=dynamic)

    @classmethod
    def from_dict(cls, raw: Optional[Mapping[str, Any]]) -> Optional["SemanticsTree"]:
        if not raw:
            return None
        annotation = SemanticsAnnotation.from_raw(raw.get("annotation"))
        children_payload = raw.get("children", {}) or {}
        children: Dict[str, SemanticsTree] = {}
        for name, payload in children_payload.items():
            child_tree = cls.from_dict(payload)
            if child_tree is not None:
                children[name] = child_tree
        dynamic = cls.from_dict(raw.get("dynamic"))
        if annotation is None and not children and dynamic is None:
            return None
        return cls(annotation=annotation, children=children, dynamic=dynamic)

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        if self.annotation is not None and not self.annotation.is_empty:
            payload["annotation"] = self.annotation.to_payload()
        if self.children:
            payload["children"] = {k: v.to_dict() for k, v in self.children.items()}
        if self.dynamic is not None:
            payload["dynamic"] = self.dynamic.to_dict()
        return payload

    def resolve(self, path: str) -> Optional[SemanticsAnnotation]:
        if path == "":
            return self.annotation
        normalized = path.replace(".", "__")
        segments = [segment for segment in normalized.split("__") if segment]
        node: Optional[SemanticsTree] = self
        annotations: List[SemanticsAnnotation] = []
        for segment in segments:
            if node is None:
                return None
            if node.annotation is not None:
                annotations.append(node.annotation)
            next_node = node.children.get(segment)
            if next_node is None and node.dynamic is not None:
                next_node = node.dynamic
            if next_node is None:
                return None
            node = next_node
        if node is not None and node.annotation is not None:
            annotations.append(node.annotation)
        return SemanticsAnnotation.combine(annotations)


@dataclass(frozen=True)
class NodeSemantics:
    """Aggregated semantics for a node's inputs and outputs."""

    inputs: Optional[SemanticsTree] = None
    outputs: Optional[SemanticsTree] = None

    @classmethod
    def from_specs(
        cls,
        inputs_spec: Optional[SocketSpec],
        outputs_spec: Optional[SocketSpec],
    ) -> Optional["NodeSemantics"]:
        inputs_tree = SemanticsTree.from_spec(inputs_spec)
        outputs_tree = SemanticsTree.from_spec(outputs_spec)
        if inputs_tree is None and outputs_tree is None:
            return None
        return cls(inputs=inputs_tree, outputs=outputs_tree)

    @classmethod
    def from_dict(cls, raw: Optional[Mapping[str, Any]]) -> Optional["NodeSemantics"]:
        if not raw:
            return None
        inputs_tree = SemanticsTree.from_dict(raw.get("inputs"))
        outputs_tree = SemanticsTree.from_dict(raw.get("outputs"))
        if inputs_tree is None and outputs_tree is None:
            return None
        return cls(inputs=inputs_tree, outputs=outputs_tree)

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        if self.inputs is not None:
            payload["inputs"] = self.inputs.to_dict()
        if self.outputs is not None:
            payload["outputs"] = self.outputs.to_dict()
        return payload

    def resolve_input(self, socket_path: str) -> Optional[SemanticsAnnotation]:
        if self.inputs is None:
            return None
        return self.inputs.resolve(socket_path)

    def resolve_output(self, socket_path: str) -> Optional[SemanticsAnnotation]:
        if self.outputs is None:
            return None
        return self.outputs.resolve(socket_path)


@dataclass(frozen=True)
class _SocketRef:
    """Lightweight pointer to a graph socket for deferred semantics resolution."""

    graph_uuid: str
    node_name: str
    socket_path: str
    kind: str  # "input" or "output"


@dataclass(frozen=True)
class SemanticsRelation:
    predicate: str
    subject: _SocketRef
    values: Tuple[Any, ...]
    label: Optional[str]
    context: Optional[Mapping[str, Any]]
    socket_label: Optional[str]


@dataclass(frozen=True)
class SemanticsPayload:
    subject: _SocketRef
    semantics: Mapping[str, Any] | SemanticsAnnotation
    socket_label: Optional[str]


def _socket_from_value(value: Any) -> Optional[BaseSocket]:
    """Return a ``BaseSocket`` from a raw value or TaggedValue proxy."""

    if isinstance(value, BaseSocket):
        return value
    if isinstance(value, TaggedValue):
        wrapped = value._socket
        return wrapped if isinstance(wrapped, BaseSocket) else None
    return None


def _socket_ref_from_value(value: Any) -> Optional[_SocketRef]:
    socket = _socket_from_value(value)
    if socket is None:
        return None
    node = getattr(socket, "_node", None)
    graph = getattr(socket, "_graph", None) or getattr(node, "graph", None)
    if node is None or graph is None:
        return None
    kind = getattr(getattr(socket, "_metadata", None), "socket_type", None)
    kind_normalized = str(kind).lower() if kind else "output"
    kind_normalized = "input" if "input" in kind_normalized else "output"
    socket_path = getattr(socket, "_scoped_name", None) or getattr(
        socket, "_name", None
    )
    if socket_path is None:
        return None
    return _SocketRef(
        graph_uuid=getattr(graph, "uuid", "<graph>"),
        node_name=getattr(node, "name", ""),
        socket_path=str(socket_path),
        kind=kind_normalized,
    )


def _graph_from_socket_value(value: Any) -> Any:
    """Return the graph object backing a socket-like value, if present."""

    socket_obj = _socket_from_value(value)
    if socket_obj is None:
        return None
    return getattr(socket_obj, "_graph", None) or getattr(
        getattr(socket_obj, "_node", None), "graph", None
    )


def _rehydrate_attachment_value(value: Any) -> Any:
    """Restore captured attachment values from serialized payloads."""

    if isinstance(value, _SocketRef):
        return value
    if isinstance(value, dict) and {
        "graph_uuid",
        "node_name",
        "socket_path",
    }.issubset(value.keys()):
        return _SocketRef(
            graph_uuid=str(value.get("graph_uuid") or "<graph>"),
            node_name=str(value.get("node_name") or ""),
            socket_path=str(value.get("socket_path") or ""),
            kind=str(value.get("kind") or "output"),
        )
    if isinstance(value, dict):
        return {k: _rehydrate_attachment_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_rehydrate_attachment_value(v) for v in value]
    if isinstance(value, tuple):
        return tuple(_rehydrate_attachment_value(v) for v in value)
    return value


def _normalize_semantics_buffer(raw: Any) -> Dict[str, List[Any]]:
    """Coerce persisted semantics buffer into runtime dataclasses."""

    if not isinstance(raw, dict):
        return {"relations": [], "payloads": []}

    normalized: Dict[str, List[Any]] = {"relations": [], "payloads": []}

    for entry in raw.get("relations", []) or []:
        if isinstance(entry, SemanticsRelation):
            normalized["relations"].append(entry)
            continue
        if not isinstance(entry, dict):
            continue
        values_raw = entry.get("values", ())
        if isinstance(values_raw, (list, tuple)):
            values: Tuple[Any, ...] = tuple(
                _rehydrate_attachment_value(v) for v in values_raw
            )
        else:
            values = (_rehydrate_attachment_value(values_raw),)
        normalized["relations"].append(
            SemanticsRelation(
                predicate=str(entry.get("predicate", "")),
                subject=_rehydrate_attachment_value(entry.get("subject")),
                values=values,
                label=entry.get("label"),
                context=entry.get("context"),
                socket_label=entry.get("socket_label"),
            )
        )

    for entry in raw.get("payloads", []) or []:
        if isinstance(entry, SemanticsPayload):
            normalized["payloads"].append(entry)
            continue
        if not isinstance(entry, dict):
            continue
        semantics_entry = entry.get("semantics")
        normalized["payloads"].append(
            SemanticsPayload(
                subject=_rehydrate_attachment_value(entry.get("subject")),
                semantics=_rehydrate_attachment_value(semantics_entry),
                socket_label=entry.get("socket_label"),
            )
        )

    return normalized


def _ensure_semantics_buffer(graph: Any) -> Dict[str, List[Any]]:
    """Ensure a graph carries a semantics buffer."""

    buffer: Optional[Dict[str, List[Any]]] = getattr(graph, SEMANTICS_BUFFER_ATTR, None)
    if buffer is None:
        normalized = {"relations": [], "payloads": []}
    else:
        normalized = _normalize_semantics_buffer(buffer)
    setattr(graph, SEMANTICS_BUFFER_ATTR, normalized)
    return normalized


def _capture_semantics_value(value: Any) -> Any:
    """Replace sockets/TaggedValues with ``_SocketRef`` markers for later resolution."""

    ref = _socket_ref_from_value(value)
    if ref is not None:
        return ref
    if isinstance(value, dict):
        return {k: _capture_semantics_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        captured = [_capture_semantics_value(v) for v in value]
        return captured if isinstance(value, list) else tuple(captured)
    return value


def attach_semantics(
    subject_or_relation: Any,
    *values: Any,
    semantics: Mapping[str, Any] | SemanticsAnnotation | None = None,
    socket_label: Optional[str] = None,
    label: Optional[str] = None,
    context: Optional[Mapping[str, Any]] = None,
) -> None:
    """Record runtime semantics attachments or relations.

    When sockets from a ``NodeGraph`` are supplied, pending semantics are
    stored on the in-memory graph for later resolution by the engine.
    """

    def _resolve_manual_semantics_value(value: Any) -> Any:
        """Leave unresolved values intact; engines resolve node references later."""

        if isinstance(value, dict):
            resolved: Dict[str, Any] = {}
            for key, nested in value.items():
                processed = _resolve_manual_semantics_value(nested)
                if processed is not None:
                    resolved[key] = processed
            return resolved
        if isinstance(value, list):
            resolved_list: List[Any] = []
            for item in value:
                processed = _resolve_manual_semantics_value(item)
                if processed is not None:
                    resolved_list.append(processed)
            return resolved_list
        return value

    if isinstance(subject_or_relation, str) and semantics is None:
        relation = subject_or_relation
        if not values:
            return
        subject = values[0]
        if subject is None:
            return
        relation_values: Tuple[Any, ...] = values[1:]
        if not relation_values:
            return

        socket_ref = _socket_ref_from_value(subject)
        if socket_ref is not None:
            graph = _graph_from_socket_value(subject)
            if graph is not None:
                buffer = _ensure_semantics_buffer(graph)
                buffer["relations"].append(
                    SemanticsRelation(
                        predicate=relation,
                        subject=socket_ref,
                        values=tuple(
                            _capture_semantics_value(val) for val in relation_values
                        ),
                        label=label,
                        context=context,
                        socket_label=socket_label,
                    )
                )
                return

        return

    subject = subject_or_relation
    if subject is None or semantics is None:
        return

    socket_ref = _socket_ref_from_value(subject)
    if socket_ref is not None:
        graph = _graph_from_socket_value(subject)
        if graph is not None:
            buffer = _ensure_semantics_buffer(graph)
            buffer["payloads"].append(
                SemanticsPayload(
                    subject=socket_ref,
                    semantics=_capture_semantics_value(semantics),
                    socket_label=socket_label,
                )
            )
            return
