from __future__ import annotations
from typing import Optional, Dict, Any, TYPE_CHECKING
from node_graph.node import Node
from node_graph.node_spec import NodeSpec

if TYPE_CHECKING:
    from node_graph.node_graph import NodeGraph


class _SpecBackedMixin:
    """Shared logic for nodes that are materialized from a NodeSpec."""

    _spec: Optional[NodeSpec] = None

    def _init_with_spec(self, spec: NodeSpec, *, embed_spec: bool = True) -> None:
        if spec is None:
            raise ValueError(f"{self.__class__.__name__} requires a spec")

        self._spec = spec
        self._executor = getattr(spec, "executor", None)
        self._error_handlers.update(getattr(spec, "error_handlers", {}))

        # mirror identity from the spec
        self.identifier = spec.identifier
        self.catalog = spec.catalog

        # persist spec reference and optionally embed the full schema
        self._metadata.setdefault(
            "spec_ref", {"identifier": spec.identifier, "version": spec.version}
        )
        if embed_spec:
            self._metadata["spec_schema"] = spec.to_dict()

        # merge user metadata last
        if getattr(spec, "metadata", None):
            self.node_type = spec.metadata.get("node_type", "Normal")
            self._metadata.update(spec.metadata)
        self._metadata["is_dynamic"] = True

        # IO from spec
        if spec.inputs is not None:
            self.inputs = self._socket_spec.SocketNamespace._from_spec(
                "inputs", spec.inputs, node=self, graph=self.graph, role="input"
            )
        if spec.outputs is not None:
            self.outputs = self._socket_spec.SocketNamespace._from_spec(
                "outputs", spec.outputs, node=self, graph=self.graph, role="output"
            )

        self._ensure_builtins()

    @property
    def spec(self) -> NodeSpec:
        return self._spec

    # share copy semantics for spec backed nodes
    def _new_for_copy(self, name: Optional[str], graph: Optional[Any]):
        embed_spec = "spec_schema" in (self._metadata or {})
        return self.__class__(
            name=name,
            uuid=None,
            graph=graph,
            spec=self._spec,
            embed_spec=embed_spec,
            executor=getattr(self, "_executor", None),
        )

    # share deserialization
    @classmethod
    def from_dict(cls, data: Dict[str, Any], graph: "NodeGraph" = None):
        spec_dict = data.get("metadata", {}).get("spec_schema")
        if spec_dict is None:
            raise ValueError(
                f"spec_schema missing in metadata for {cls.__name__}.from_dict"
            )
        spec = NodeSpec.from_dict(spec_dict)
        obj = cls(spec=spec, name=data["name"], graph=graph, uuid=data.get("uuid"))
        obj.update_from_dict(data)
        return obj


class SpecNode(_SpecBackedMixin, Node):
    """Concrete node materialized from a NodeSpec."""

    identifier: str = "node_graph.spec_node"

    def __init__(
        self, *args, spec: NodeSpec, embed_spec: bool = True, **kwargs
    ) -> None:
        super().__init__(*args, **kwargs)
        self._init_with_spec(spec, embed_spec=embed_spec)
