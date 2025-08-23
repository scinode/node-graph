from __future__ import annotations
from typing import Any, Dict

from node_graph.node import Node
from node_graph.node_graph import NodeGraph
from node_graph.socket_spec import SocketSpec


class SubGraphNode(Node):
    """Wrap a NodeGraph instance so it can be used as a Node in a parent graph.

    - Inputs mirror the child graph's *graph_inputs* namespace
    - Outputs mirror the child graph's *graph_outputs* namespace
    - We embed the child graph's serialized dict in metadata for persistence
    """

    identifier: str = "node_graph.subgraph"

    def __init__(
        self,
        *,
        subgraph: NodeGraph,
        name: str | None = None,
        uuid: str | None = None,
        graph=None,
        parent=None,
        metadata: Dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            name=name or subgraph.name,
            uuid=uuid,
            graph=graph,
            parent=parent,
            metadata=metadata,
        )
        self.subgraph: NodeGraph = subgraph
        # snapshot the child graph into metadata so we can restore without a registry
        self._metadata["embedded_graph"] = self.subgraph.to_dict()

        # mirror IO from the child graph
        in_spec = SocketSpec.from_namespace(self.subgraph.graph_inputs.inputs)
        out_spec = SocketSpec.from_namespace(self.subgraph.graph_outputs.inputs)
        self.inputs = self._SocketNamespaceClass._from_spec(
            "inputs", in_spec, node=self, graph=self.graph, role="input"
        )
        self.outputs = self._SocketNamespaceClass._from_spec(
            "outputs", out_spec, node=self, graph=self.graph, role="output"
        )

        # ensure builtin wait/output sockets exist
        if "_outputs" not in self.outputs:
            self.add_output("node_graph.any", "_outputs")
        if "_wait" not in self.outputs:
            self.add_output(
                "node_graph.any",
                "_wait",
                link_limit=100000,
                metadata={"arg_type": "none"},
            )
        if "_wait" not in self.inputs:
            self.add_input(
                "node_graph.any",
                "_wait",
                link_limit=100000,
                metadata={"arg_type": "none"},
            )

    @property
    def nodes(self):
        """Return the child graph's nodes."""
        return self.subgraph.nodes

    @property
    def links(self):
        """Return the child graph's links."""
        return self.subgraph.links

    def refresh_io_from_subgraph(self) -> None:
        """Rebuild this node's inputs/outputs from the current child graph."""
        in_spec = SocketSpec.from_namespace(self.subgraph.graph_inputs.inputs)
        out_spec = SocketSpec.from_namespace(self.subgraph.graph_outputs.inputs)
        self.inputs = self._SocketNamespaceClass._from_spec(
            "inputs", in_spec, node=self, graph=self.graph, role="input"
        )
        self.outputs = self._SocketNamespaceClass._from_spec(
            "outputs", out_spec, node=self, graph=self.graph, role="output"
        )
        if "_outputs" not in self.outputs:
            self.add_output("node_graph.any", "_outputs")
        if "_wait" not in self.outputs:
            self.add_output(
                "node_graph.any",
                "_wait",
                link_limit=100000,
                metadata={"arg_type": "none"},
            )
        if "_wait" not in self.inputs:
            self.add_input(
                "node_graph.any",
                "_wait",
                link_limit=100000,
                metadata={"arg_type": "none"},
            )

    def to_dict(
        self, short: bool = False, should_serialize: bool = False
    ) -> Dict[str, Any]:
        # update embedded graph snapshot before exporting
        self._metadata["embedded_graph"] = self.subgraph.to_dict()
        return super().to_dict(short=short, should_serialize=should_serialize)

    @classmethod
    def from_dict(
        cls, data: Dict[str, Any], graph: NodeGraph | None = None
    ) -> "SubGraphNode":
        md = data.get("metadata", {}) or {}
        emb = md.get("embedded_graph")
        if not emb:
            raise ValueError(
                "SubGraphNode.from_dict: missing embedded_graph in metadata"
            )
        child = NodeGraph.from_dict(emb)
        node = cls(
            subgraph=child, name=data.get("name"), uuid=data.get("uuid"), graph=graph
        )
        node.update_from_dict(data)
        return node
