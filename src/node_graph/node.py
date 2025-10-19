from __future__ import annotations
from uuid import uuid1
from node_graph.registry import RegistryHub, registry_hub
from typing import List, Optional, Dict, Any, Union
from node_graph.utils import deep_copy_only_dicts
from .socket import WaitingOn
from node_graph_widget import NodeGraphWidget
from node_graph.collection import (
    PropertyCollection,
)
from .executor import SafeExecutor, BaseExecutor
from .error_handler import ErrorHandlerSpec
from node_graph.socket_spec import SocketSpecAPI
from .config import BuiltinPolicy
from .node_spec import NodeSpec
from dataclasses import replace
from .mixins import IOOwnerMixin, WidgetRenderableMixin, WaitableMixin


class Node(WidgetRenderableMixin, IOOwnerMixin, WaitableMixin):
    """Base class for Node.

    Attributes:
        identifier (str): The identifier is used for loading the Node.
        node_type (str): Type of this node. Possible values are "Normal", "REF", "GROUP".

    Examples:
        Add nodes:
        >>> float1 = ng.add_node("TestFloat", name="float1")
        >>> add1 = ng.add_node("TestDelayAdd", name="add1")

        Copy node:
        >>> n = node.copy(name="new_name")

        Append node to node graph:
        >>> ng.append_node(node)

    """

    _REGISTRY: Optional[RegistryHub] = registry_hub
    _PROPERTY_CLASS = PropertyCollection
    _SOCKET_SPEC_API = SocketSpecAPI
    _BUILTINS_POLICY = BuiltinPolicy()

    _default_spec = NodeSpec(
        identifier="node_graph.node",
        node_type="Normal",
        inputs=_SOCKET_SPEC_API.namespace(),
        outputs=_SOCKET_SPEC_API.namespace(),
        catalog="Base",
        base_class_path="node_graph.node.Node",
    )

    def __init__(
        self,
        name: Optional[str] = None,
        uuid: Optional[str] = None,
        graph: Optional["NodeGraph"] = None,
        spec: Optional[NodeSpec] = None,
        parent: Optional[Node] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Initialize the Node.

        Args:
            name (str, optional): Name of the node. Defaults to None.
            uuid (str, optional): UUID of the node. Defaults to None.
            graph (Any, optional): The node graph this node belongs to. Defaults to None.
        """

        self.spec = spec or self._default_spec
        self.identifier = self.spec.identifier
        self.node_type = self.spec.node_type
        self.name = name or self.spec.identifier
        self.uuid = uuid or str(uuid1())
        self.graph = graph
        self.parent = parent
        self._metadata = metadata or {}
        self.properties = self._PROPERTY_CLASS(self, pool=self._REGISTRY.property_pool)

        self.state = "CREATED"
        self.action = "NONE"
        self.position = [30, 30]
        self.description = ""
        self.log = ""

        # Materialize the runtime objects from the spec
        self._materialize_from_spec()

        self.create_properties()
        # call update_spec once for the properties to take effect
        # in case the the properties has callback to update the spec
        self.update_spec()

        self._args_data = None
        self._widget = None
        self._waiting_on = WaitingOn(node=self, graph=self.graph)

    def _materialize_from_spec(self) -> None:
        """
        Builds the runtime properties and sockets from the current self.spec.
        This is the bridge between the static definition (spec) and the live object.
        """
        # Materialize IO from spec
        input_spec = self.spec.inputs or self._SOCKET_SPEC_API.namespace()
        output_spec = self.spec.outputs or self._SOCKET_SPEC_API.namespace()
        if input_spec is not None:
            self.inputs = self._SOCKET_SPEC_API.SocketNamespace._from_spec(
                "inputs", input_spec, node=self, graph=self.graph, role="input"
            )
        if output_spec is not None:
            self.outputs = self._SOCKET_SPEC_API.SocketNamespace._from_spec(
                "outputs", output_spec, node=self, graph=self.graph, role="output"
            )

        self._ensure_builtins()

    def _ensure_builtins(self) -> None:
        """Create built-in sockets based on policy."""
        from node_graph.config import (
            WAIT_SOCKET_NAME,
            OUTPUT_SOCKET_NAME,
            MAX_LINK_LIMIT,
        )

        if self._BUILTINS_POLICY.input_wait and WAIT_SOCKET_NAME not in self.inputs:
            self.add_input(
                self._REGISTRY.socket_pool.any,
                WAIT_SOCKET_NAME,
                link_limit=MAX_LINK_LIMIT,
                metadata={
                    "required": False,
                    "arg_type": "none",
                    "builtin_socket": True,
                },
            )
        if (
            self._BUILTINS_POLICY.default_output
            and OUTPUT_SOCKET_NAME not in self.outputs
        ):
            self.add_output(
                self._REGISTRY.socket_pool.any,
                OUTPUT_SOCKET_NAME,
                metadata={"required": False, "builtin_socket": True},
            )
        if self._BUILTINS_POLICY.output_wait and WAIT_SOCKET_NAME not in self.outputs:
            self.add_output(
                self._REGISTRY.socket_pool.any,
                WAIT_SOCKET_NAME,
                link_limit=MAX_LINK_LIMIT,
                metadata={"required": False, "builtin_socket": True},
            )

    @property
    def widget(self) -> NodeGraphWidget:
        if self._widget is None:
            self._widget = NodeGraphWidget(
                settings={"minmap": False},
                style={"width": "80%", "height": "600px"},
            )
        return self._widget

    def add_property(self, identifier: str, name: str, **kwargs) -> Any:
        prop = self.properties._new(identifier, name, **kwargs)
        return prop

    def get_property_names(self) -> List[str]:
        return self.properties._get_keys()

    def create_properties(self) -> None:
        """Create properties for this node."""

    def update_spec(self) -> None:
        """Create input and output sockets for this node."""
        pass

    def reset(self) -> None:
        """Reset this node and all its child nodes to "CREATED"."""

    def to_dict(
        self, include_sockets: bool = False, should_serialize: bool = False
    ) -> Dict[str, Any]:
        """Save all datas, include properties, input and output sockets."""

        metadata = self.get_metadata()
        properties = self.export_properties()
        data = {
            "identifier": self.identifier,
            "uuid": self.uuid,
            "name": self.name,
            "state": self.state,
            "action": self.action,
            "error": "",
            "metadata": metadata,
            "spec": self.spec.to_dict(),
            "properties": properties,
            "inputs": self.inputs._value,
            "position": self.position,
            "description": self.description,
            "log": self.log,
            "hash": "",  # we can only calculate the hash during runtime when all the data is ready
        }
        if include_sockets:
            data["input_sockets"] = self.inputs._to_dict()
            data["output_sockets"] = self.outputs._to_dict()
        # to avoid some dict has the same address with others nodes
        # which happens when {} is used as default value
        # we copy the value only
        data = deep_copy_only_dicts(data)
        if should_serialize:
            self.serialize_data(data)
        return data

    def serialize_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Serialize the node for database storage.
        This should be overrided by the subclass."""
        pass

    @property
    def metadata(self) -> Dict[str, Any]:
        return self.get_metadata()

    def get_metadata(self) -> Dict[str, Any]:
        """Export metadata to a dictionary."""
        metadata = self._metadata.copy()
        return metadata

    @property
    def args_data(self) -> Dict[str, List]:
        if self._args_data is None:
            self._args_data = self.get_args_data()
        return self._args_data

    def get_args_data(self) -> Dict[str, List]:
        """Get all the args data from properties and inputs."""
        from node_graph.utils import get_arg_type

        args_data = {
            "args": [],
            "kwargs": [],
            "var_args": None,
            "var_kwargs": None,
        }
        for prop in self.properties:
            get_arg_type(prop.name, args_data, prop.arg_type)
        for input in self.inputs:
            get_arg_type(
                input._name,
                args_data,
                input._metadata.arg_type,
            )
        return args_data

    def export_properties(self) -> List[Dict[str, Any]]:
        """Export properties to a dictionary.
        This data will be used for calculation.
        """
        properties = {}
        for prop in self.properties:
            properties[prop.name] = prop.to_dict()
        return properties

    def export_executor_to_dict(self) -> Optional[Dict[str, Union[str, bool]]]:
        """Export executor to a dictionary.
        Three kinds of executor:
        - Python built-in function. e.g. getattr
        - User defined function
        - User defined class.
        """
        executor = self.get_executor()
        if executor is None:
            return executor
        if isinstance(executor, dict):
            executor = SafeExecutor(**executor)
        return executor.to_dict()

    @classmethod
    def from_dict(cls, data: Dict[str, Any], graph: "NodeGraph" = None) -> Any:
        """
        Factory method to rebuild a Node from dict data, handling persistence modes.
        """
        if "spec" in data:
            spec_dict = data["spec"]
            spec = NodeSpec.from_dict(spec_dict)
            node = spec.to_node(name=data["name"], graph=graph, uuid=data.get("uuid"))
            graph.nodes._append(node)
        else:
            identifier = data["metadata"]["identifier"]
            node = graph.add_node(
                identifier,
                name=data["name"],
                uuid=data.pop("uuid", None),
            )
        # then load the properties
        node.update_from_dict(data)
        return node

    def update_from_dict(self, data: Dict[str, Any]) -> None:
        """udpate node from dict data. Set metadata and properties.
        This method can be overrided.
        """

        for key in ["uuid", "state", "action", "description", "hash", "position"]:
            if data.get(key):
                setattr(self, key, data.get(key))
        # properties first, because the socket may be dynamic
        for name, prop in data.get("properties", {}).items():
            self.properties[name].value = prop["value"]
        # inputs
        self.inputs._set_socket_value(data.get("inputs", {}))

    @classmethod
    def load(cls, uuid: str) -> None:
        """Load Node data from database."""

    @classmethod
    def new(
        cls,
        identifier: str,
        name: Optional[str] = None,
        NodePool: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Create a node from a identifier.
        When a plugin create a node, it should provide its own node pool.
        Then call super().new(identifier, name, NodePool) to create a node.
        """
        from node_graph.collection import get_item_class

        if NodePool is None:
            from node_graph.nodes import NodePool

        ItemClass = get_item_class(identifier, NodePool)
        node = ItemClass(name=name, metadata=metadata)
        return node

    def _new_for_copy(
        self, name: Optional[str], graph: Optional[Any], spec: NodeSpec
    ) -> Any:
        """Factory hook used by copy(); subclasses can override to supply ctor args."""
        return self.__class__(name=name, uuid=None, graph=graph, spec=spec)

    def copy(
        self,
        name: Optional[str] = None,
        graph: Optional[Any] = None,
    ) -> Any:
        """Copy a node.

        Copy a node to a new node. If graph is None, the node will be copied inside the same graph,
        otherwise the node will be copied to a new graph.
        The properties, inputs and outputs will be copied.

        Args:
            name (str, optional): _description_. Defaults to None.
            graph (NodeGraph, optional): _description_. Defaults to None.

        Returns:
            Node: _description_
        """
        if graph is not None:
            # copy node to a new graph, keep the name
            name = self.name if name is None else name
        else:
            # copy node inside the same graph, change the name
            graph = self.graph
            name = f"{self.name}_copy" if name is None else name
        node = self._new_for_copy(name=name, graph=graph, spec=self.spec)
        # becareful when copy the properties, the value should be copied
        # it will update the sockets, so we copy the properties first
        # then overwrite the sockets
        for i in range(len(self.properties)):
            node.properties[i].value = self.properties[i].value
        node.inputs._set_socket_value(self.inputs._value)
        return node

    def get_executor(self) -> Optional[BaseExecutor]:
        """Get the default executor."""
        return self.spec.executor

    @property
    def error_handlers(self) -> Dict[str, ErrorHandlerSpec]:
        return self.get_error_handlers()

    def get_error_handlers(self) -> Dict[str, ErrorHandlerSpec]:
        """Get the error handlers."""
        error_handlers = self.spec.error_handlers or {}
        error_handlers.update(self.spec.attached_error_handlers or {})
        return error_handlers

    def add_error_handler(self, error_handler: ErrorHandlerSpec | dict) -> None:
        """Add an error handler to this node."""
        from node_graph.error_handler import normalize_error_handlers

        error_handlers = normalize_error_handlers(error_handler)
        attached_error_handlers = self.spec.attached_error_handlers or {}
        attached_error_handlers.update(error_handlers)
        self.spec = replace(self.spec, attached_error_handlers=attached_error_handlers)

    def execute(self):
        """Execute the node."""
        from node_graph.node_spec import BaseHandle

        executor = self.get_executor().callable
        # the imported executor could be a wrapped function
        if isinstance(executor, BaseHandle) and hasattr(executor, "_callable"):
            executor = getattr(executor, "_callable")
        inputs = self.inputs._value
        args = [inputs[arg] for arg in self.args_data["args"]]
        kwargs = {key: inputs[key] for key in self.args_data["kwargs"]}
        var_kwargs = (
            inputs[self.args_data["var_kwargs"]]
            if self.args_data["var_kwargs"]
            else None
        )
        if var_kwargs is None:
            result = executor(*args, **kwargs)
        else:
            result = executor(*args, **kwargs, **var_kwargs)
        return result

    def get_results(self) -> None:
        """Item data from database"""

    def update(self) -> None:
        """Update node state."""

    @property
    def results(self) -> None:
        return self.get_results()

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}(name='{self.name}', properties=[{', '.join(repr(k) for k in self.get_property_names())}], "
            f"inputs=[{', '.join(repr(k) for k in self.get_input_names())}], "
            f"outputs=[{', '.join(repr(k) for k in self.get_output_names())}])"
        )

    def set_inputs(self, data: Dict[str, Any]) -> None:
        """Set properties by a dict.

        Args:
            data (dict): _description_
        """

        data = deep_copy_only_dicts(data)
        for key, value in data.items():
            # if the value is a node, link the node's top-level output to the input
            if value is None:
                continue
            if isinstance(value, Node):
                self.graph.add_link(value.outputs["_outputs"], self.inputs[key])
                continue
            if key in self.properties:
                self.properties[key].value = value
            else:
                self.inputs._set_socket_value({key: value})

    def get(self, key: str) -> Any:
        """Get the value of property by key.

        Args:
            key (_type_): _description_

        Returns:
            _type_: _description_
        """
        return self.properties[key].value

    def save(self) -> None:
        """Modify and save a node to database."""

    def to_widget_value(self):
        tdata = self.to_dict(include_sockets=True)

        for key in ("properties", "executor", "node_class", "process", "input_values"):
            tdata.pop(key, None)
        inputs = []
        for input in tdata["input_sockets"]["sockets"].values():
            input.pop("property", None)
            inputs.append(input)

        tdata["inputs"] = inputs

        tdata["label"] = tdata["identifier"]

        wgdata = {"name": self.name, "nodes": {self.name: tdata}, "links": []}
        return wgdata
