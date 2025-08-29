from __future__ import annotations
from abc import ABC
from typing import Any, Dict, Optional
from node_graph.socket_spec import SocketSpec, BaseSocketSpecAPI
from node_graph.socket import NodeSocketNamespace
from dataclasses import dataclass
from node_graph.config import BuiltinSocketNames, MAX_LINK_LIMIT


@dataclass(frozen=True)
class BuiltinPolicy:
    input_wait: bool = True
    output_wait: bool = True
    default_output: bool = True


class GraphIOBase(ABC):
    """Abstract base for anything that owns **inputs/outputs** sockets in a graph.

    Subclasses must provide:
      - self.name: str
      - self.registry (with .type_mapping)
      - self.graph  (for NodeGraph, graph==self; for Node, graph is the parent graph)

    They may override:
      - _SocketNamespaceClass
      - _socket_spec_api
      - owner_label_suffix
    """

    _socket_spec_api = BaseSocketSpecAPI
    owner_label_suffix = "_graph"  # used to disambiguate NodeGraph owners from Nodes
    Builtins: BuiltinPolicy = BuiltinPolicy()

    def _init_socket_namespaces(
        self,
        *,
        inputs: Optional[SocketSpec | Dict[str, Any]] = None,
        outputs: Optional[SocketSpec | Dict[str, Any]] = None,
    ) -> None:
        """Materialize inputs/outputs namespaces with correct ownership.

        Ensures:
          - each child socket has `_node` set to this owner
          - each child socket has `_graph` set to `owner_graph()`
          - `_scoped_name` looks like "inputs.x" / "outputs.y"
        """

        inputs = self._socket_spec_api.validate_socket_data(inputs)
        outputs = self._socket_spec_api.validate_socket_data(outputs)

        if inputs is None:
            inputs = self._socket_spec_api.namespace()
        if outputs is None:
            outputs = self._socket_spec_api.namespace()

        g = self.owner_graph()
        self._inputs = self._socket_spec_api.SocketNamespace._from_spec(
            "inputs", inputs, node=self, graph=g, role="input"
        )
        self._outputs = self._socket_spec_api.SocketNamespace._from_spec(
            "outputs", outputs, node=self, graph=g, role="output"
        )

        # ergonomic defaults for fan-out on dynamic namespaces
        if hasattr(self.inputs, "_metadata"):
            self.inputs._metadata.sub_socket_default_link_limit = 1_000_000
        self._ensure_builtins()

    def _ensure_builtins(self, policy: Optional[BuiltinPolicy] = None) -> None:
        """Create built-in sockets based on policy."""
        policy = policy or self.Builtins

        if policy.input_wait and BuiltinSocketNames.wait not in self.inputs:
            self.add_input(
                self.SocketPool.any,
                BuiltinSocketNames.wait,
                link_limit=MAX_LINK_LIMIT,
                metadata={"arg_type": "none", "builtin_socket": True},
            )
        if policy.default_output and BuiltinSocketNames.output not in self.outputs:
            self.add_output(
                self.SocketPool.any,
                BuiltinSocketNames.output,
                metadata={"builtin_socket": True},
            )
        if policy.output_wait and BuiltinSocketNames.wait not in self.outputs:
            self.add_output(
                self.SocketPool.any,
                BuiltinSocketNames.wait,
                link_limit=MAX_LINK_LIMIT,
                metadata={"arg_type": "none", "builtin_socket": True},
            )

    @property
    def inputs(self) -> NodeSocketNamespace:
        """Group inputs node."""
        return self._inputs

    @inputs.setter
    def inputs(self, value: Dict[str, Any]) -> None:
        """Set group inputs node."""
        self._inputs._set_socket_value(value)

    @property
    def outputs(self) -> NodeSocketNamespace:
        """Group outputs node."""
        return self._outputs

    @outputs.setter
    def outputs(self, value: Dict[str, Any]) -> None:
        """Set group outputs node."""
        self._outputs._set_socket_value(value)

    def owner_graph(self):
        """Return the NodeGraph that owns this element (NodeGraph returns itself)."""
        g = getattr(self, "graph", None)
        return g if g is not None else self

    def owner_label(self) -> str:
        """Stable, non-colliding label for link endpoints and UI serialization."""
        base = getattr(self, "name", self.__class__.__name__)
        # Disambiguate graphs from nodes with the same name.
        if self.owner_graph() is self:
            return f"{base}{self.owner_label_suffix}"
        return base

    def snapshot_specs(self) -> Dict[str, Any]:
        """Return inputs_spec/outputs_spec for persistence."""
        tm = (
            getattr(self.registry, "type_mapping", {})
            if hasattr(self, "registry")
            else {}
        )
        return {
            "inputs_spec": SocketSpec.from_namespace(
                self.inputs, type_mapping=tm
            ).to_dict(),
            "outputs_spec": SocketSpec.from_namespace(
                self.outputs, type_mapping=tm
            ).to_dict(),
        }


class GraphCtxMixin:
    """Mixin that adds **ctx** namespace and its serialization.

    Requires the subclass to also inherit GraphIOBase (for owner_graph, _SocketNamespaceClass, _socket_spec_api).
    """

    def _init_ctx_namespace(
        self, ctx: Optional[SocketSpec | Dict[str, Any]] = None
    ) -> None:
        ctx = self._socket_spec_api.validate_socket_data(ctx)
        if ctx is None:
            ctx = self._socket_spec_api.dynamic("any")
        g = self.owner_graph()
        self._ctx = self._socket_spec_api.SocketNamespace._from_spec(
            "ctx", ctx, node=self, graph=g, role="input"
        )
        if hasattr(self._ctx, "_metadata"):
            self._ctx._metadata.sub_socket_default_link_limit = 1_000_000

    @property
    def ctx(self) -> NodeSocketNamespace:
        """Context node."""
        return self._ctx

    @ctx.setter
    def ctx(self, value: Dict[str, Any]) -> None:
        """Set context node."""
        self._ctx._clear()
        self._ctx._set_socket_value(value, link_limit=100000)

    def snapshot_ctx_spec(self) -> Dict[str, Any]:
        tm = (
            getattr(self.registry, "type_mapping", {})
            if hasattr(self, "registry")
            else {}
        )
        from node_graph.socket_spec import SocketSpec as _SS

        return {"ctx_spec": _SS.from_namespace(self.ctx, type_mapping=tm).to_dict()}
