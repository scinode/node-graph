from __future__ import annotations
from typing import List, Protocol
from node_graph.collection import DependencyCollection
from .socket import BaseSocket, NodeSocketNamespace
from .socket_spec import SocketSpec, add_spec_field
from .node_spec import SchemaSource
from dataclasses import replace


class _HasSocketNamespaces(Protocol):
    inputs: NodeSocketNamespace
    outputs: NodeSocketNamespace


class IOOwnerMixin(_HasSocketNamespaces):
    """Shared helpers for objects that expose inputs/outputs namespaces."""

    def add_input(self, identifier: str, name: str, **kwargs):
        return self.inputs._new(identifier, name, **kwargs)

    def add_output(self, identifier: str, name: str, **kwargs):
        return self.outputs._new(identifier, name, **kwargs)

    def get_input_names(self) -> List[str]:
        return self.inputs._get_keys()

    def get_output_names(self) -> List[str]:
        return self.outputs._get_keys()

    def add_input_spec(self, spec: str | SocketSpec, name: str, **kwargs) -> BaseSocket:
        """
        Permanently adds an input socket to the node's spec.
        This marks the node as modified and will be persisted.
        """
        if isinstance(spec, str):
            spec = SocketSpec(identifier=spec, **kwargs)
        new_inputs_spec = add_spec_field(self.spec.inputs, name, spec)
        # This is an explicit, permanent modification
        self.spec = replace(
            self.spec, schema_source=SchemaSource.EMBEDDED, inputs=new_inputs_spec
        )
        # add the socket to the runtime object
        self._SOCKET_SPEC_API.SocketNamespace._append_from_spec(
            self.inputs,
            name,
            spec,
            node=self.inputs._node,
            graph=self.inputs._graph,
            role="input",
        )
        return self.inputs[name]

    def add_output_spec(
        self, spec: str | SocketSpec, name: str, **kwargs
    ) -> BaseSocket:
        """
        Permanently adds an output socket to the node's spec.
        This marks the node as modified and will be persisted.
        """
        if isinstance(spec, str):
            spec = SocketSpec(identifier=spec, **kwargs)
        new_outputs_spec = add_spec_field(self.spec.outputs, name, spec)
        # This is an explicit, permanent modification
        self.spec = replace(
            self.spec, schema_source=SchemaSource.EMBEDDED, outputs=new_outputs_spec
        )
        # add the socket to the runtime object
        self._SOCKET_SPEC_API.SocketNamespace._append_from_spec(
            self.outputs,
            name,
            spec,
            node=self.outputs._node,
            graph=self.outputs._graph,
            role="output",
        )
        return self.outputs[name]


class WidgetRenderableMixin:
    """Unify widget plumbing. Subclasses implement to_widget_value()."""

    _widget = None

    @property
    def widget(self):
        from node_graph_widget import NodeGraphWidget

        if self._widget is None:
            # Node currently sets custom settings; keep defaults generic here.
            self._widget = NodeGraphWidget()
        return self._widget

    def _repr_mimebundle_(self, *args, **kwargs):
        # if ipywdigets > 8.0.0, use _repr_mimebundle_ instead of _ipython_display_
        self.widget.value = self.to_widget_value()
        if hasattr(self.widget, "_repr_mimebundle_"):
            return self.widget._repr_mimebundle_(*args, **kwargs)
        return self.widget._ipython_display_(*args, **kwargs)

    def to_html(self, output: str = None, **kwargs):
        """Write a standalone html file to visualize the task."""
        self.widget.value = self.to_widget_value()
        return self.widget.to_html(output=output, **kwargs)


class WaitableMixin:
    """Share >> / << dependency chaining using WaitingOn helper."""

    def __rshift__(self, other: "Node" | BaseSocket | DependencyCollection):
        """
        Called when we do: self >> other
        So we link them or mark that 'other' must wait for 'self'.
        """
        if isinstance(other, DependencyCollection):
            for item in other.items:
                self >> item
        else:
            other._waiting_on.add(self)
        return other

    def __lshift__(self, other: "Node" | BaseSocket | DependencyCollection):
        """
        Called when we do: self << other
        Means the same as: other >> self
        """
        if isinstance(other, DependencyCollection):
            for item in other.items:
                self << item
        else:
            self._waiting_on.add(other)
        return other
