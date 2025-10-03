from __future__ import annotations
from typing import Any, Dict, Optional

from node_graph.node import BuiltinPolicy, Node
from node_graph.node_spec import NodeSpec


class _GraphIOSharedMixin:
    """Make inputs and outputs physically share the same namespace object.

    Guarantees after any lifecycle step:
      - self.outputs is self.inputs
      - builtins are disabled for wait and default output
    """

    # turn off framework builtins for these graph-level nodes
    _BUILTINS_POLICY = BuiltinPolicy(
        input_wait=False, output_wait=False, default_output=False
    )

    def _unify_io(self) -> None:
        """Point outputs to the exact same object as inputs."""
        # if subclasses rebuilt inputs, just mirror it over
        self.outputs = self.inputs

    # ensure the alias is kept
    def update_spec(self) -> None:
        super().update_spec()
        self._unify_io()

    # make sure copying preserves the alias
    def copy(self, name: Optional[str] = None, graph: Optional[Any] = None):
        new_obj = super().copy(name=name, graph=graph)
        new_obj.outputs = new_obj.inputs
        return new_obj

    # keep the alias after deserialization
    @classmethod
    def from_dict(cls, data: Dict[str, Any], graph: "NodeGraph" = None):
        obj = super().from_dict(
            data, graph
        )  # SpecNode/SpecTask uses cls(...) internally
        obj.outputs = obj.inputs
        return obj


class GraphLevelNode(_GraphIOSharedMixin, Node):
    """Graph level node where inputs and outputs are the same sockets."""

    identifier: str = "node_graph.graph_level"
    catalog: str = "Builtins"
    is_dynamic: bool = True

    _default_spec = NodeSpec(
        identifier="node_graph.graph_level",
        catalog="Builtins",
        base_class_path="node_graph.nodes.builtins.GraphLevelNode",
    )

    def __init__(self, *args, **kwargs):
        # SpecNode handles spec application and may rebuild inputs/outputs
        super().__init__(*args, **kwargs)
        self._unify_io()
