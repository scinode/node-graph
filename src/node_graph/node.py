from uuid import uuid1
from node_graph.sockets import SocketPool
from node_graph.properties import PropertyPool
from typing import List, Optional, Dict, Any, Union
from node_graph.utils import deep_copy_only_dicts
from node_graph.socket import NodeSocket, NodeSocketNamespace
from node_graph_widget import NodeGraphWidget
from node_graph.collection import (
    PropertyCollection,
)
from node_graph.executor import NodeExecutor


class Node:
    """Base class for Node.

    Attributes:
        identifier (str): The identifier is used for loading the Node.
        node_type (str): Type of this node. Possible values are "Normal", "REF", "GROUP".
        parent_uuid (str): UUID of the node graph this node belongs to.

    Examples:
        Add nodes:
        >>> float1 = ng.add_node("TestFloat", name="float1")
        >>> add1 = ng.add_node("TestDelayAdd", name="add1")

        Copy node:
        >>> n = node.copy(name="new_name")

        Append node to node graph:
        >>> ng.append_node(node)

    """

    # This is the entry point for the socket and property pool
    SocketPool = SocketPool
    PropertyPool = PropertyPool
    InputCollectionClass = NodeSocketNamespace
    OutputCollectionClass = NodeSocketNamespace
    PropertyCollectionClass = PropertyCollection

    identifier: str = "Node"
    default_name: str = None
    node_type: str = "Normal"
    parent_uuid: str = ""
    catalog: str = "Node"
    group_properties: List[List[str]] = None
    group_inputs: List[List[str]] = None
    group_outputs: List[List[str]] = None
    is_dynamic: bool = False

    def __init__(
        self,
        name: Optional[str] = None,
        uuid: Optional[str] = None,
        parent: Optional[Any] = None,
        metadata: Optional[Dict[str, Any]] = None,
        executor: Optional[NodeExecutor] = None,
    ) -> None:
        """Initialize the Node.

        Args:
            name (str, optional): Name of the node. Defaults to None.
            uuid (str, optional): UUID of the node. Defaults to None.
            parent (Any, optional): Parent node. Defaults to None.
        """
        self.name = name or self.identifier
        self.uuid = uuid or str(uuid1())
        self.parent = parent
        self._metadata = metadata or {}
        self._executor = executor
        self.properties = self.PropertyCollectionClass(self, pool=self.PropertyPool)
        self.inputs = self.InputCollectionClass(
            "inputs", node=self, pool=self.SocketPool
        )
        self.outputs = self.OutputCollectionClass(
            "outputs", node=self, pool=self.SocketPool
        )
        self.state = "CREATED"
        self.action = "NONE"
        self.position = [30, 30]
        self.description = ""
        self.log = ""
        self.create_properties()
        self.create_sockets()
        self._args_data = None
        self._widget = NodeGraphWidget(
            settings={"minmap": False},
            style={"width": "80%", "height": "600px"},
        )

    @classmethod
    def generate_name(cls) -> str:
        cls.get_executor()["callable_name"]

    def add_input(self, identifier: str, name: str, **kwargs) -> NodeSocket:
        """Add an input socket to this node."""

        input = self.inputs._new(identifier, name, **kwargs)
        return input

    def add_output(self, identifier: str, name: str, **kwargs) -> NodeSocket:
        output = self.outputs._new(identifier, name, **kwargs)
        return output

    def add_property(self, identifier: str, name: str, **kwargs) -> Any:
        prop = self.properties._new(identifier, name, **kwargs)
        return prop

    def get_input_names(self) -> List[str]:
        return self.inputs._get_keys()

    def get_output_names(self) -> List[str]:
        return self.outputs._get_keys()

    def get_property_names(self) -> List[str]:
        return self.properties._get_keys()

    def create_properties(self) -> None:
        """Create properties for this node."""
        self.properties._clear()

    def create_sockets(self) -> None:
        """Create input and output sockets for this node."""
        self.inputs._clear()
        self.outputs._clear()

    def reset(self) -> None:
        """Reset this node and all its child nodes to "CREATED"."""

    def to_dict(self, short: bool = False) -> Dict[str, Any]:
        """Save all datas, include properties, input and output sockets."""

        if short:
            data = {
                "name": self.name,
                "identifier": self.identifier,
                "node_type": self.node_type,
                "uuid": self.uuid,
            }
        else:
            metadata = self.get_metadata()
            properties = self.export_properties()
            input_sockets = self.inputs._to_dict()
            output_sockets = self.outputs._to_dict()
            executor = self.export_executor_to_dict()
            data = {
                "identifier": self.identifier,
                "uuid": self.uuid,
                "name": self.name,
                "state": self.state,
                "action": self.action,
                "error": "",
                "metadata": metadata,
                "properties": properties,
                "inputs": input_sockets,
                "outputs": output_sockets,
                "executor": executor,
                "position": self.position,
                "description": self.description,
                "log": self.log,
                "hash": "",  # we can only calculate the hash during runtime when all the data is ready
            }
        # to avoid some dict has the same address with others nodes
        # which happens when {} is used as default value
        # we copy the value only
        data = deep_copy_only_dicts(data)
        return data

    @property
    def metadata(self) -> Dict[str, Any]:
        return self.get_metadata()

    def get_metadata(self) -> Dict[str, Any]:
        """Export metadata to a dictionary."""
        metadata = self._metadata
        metadata.update(
            {
                "node_type": self.node_type,
                "catalog": self.catalog,
                "parent_uuid": self.parent.uuid if self.parent else self.parent_uuid,
                "group_properties": self.group_properties
                if self.group_properties
                else [],
                "group_inputs": self.group_inputs if self.group_inputs else [],
                "group_outputs": self.group_outputs if self.group_outputs else [],
                "is_dynamic": self.is_dynamic,
            }
        )
        # also save the parent class information
        metadata["node_class"] = {
            "callable_name": super().__class__.__name__,
            "module_path": super().__class__.__module__,
        }
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
                input._metadata.get("arg_type", "kwargs"),
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
            executor = NodeExecutor(**executor)
        return executor.to_dict()

    @classmethod
    def from_dict(
        cls, data: Dict[str, Any], NodePool: Optional[Dict[str, Any]] = None
    ) -> Any:
        """Rebuild Node from dict data."""
        from node_graph.utils import get_executor_from_path

        if NodePool is None:
            from node_graph.nodes import NodePool

        # first create the node instance
        if data.get("metadata", {}).get("is_dynamic", False):
            FactoryClass = get_executor_from_path(data["metadata"]["factory_class"])
            node_class = FactoryClass(data)
        else:
            node_class = NodePool[data["identifier"].lower()].load()

        node = node_class(name=data["name"], uuid=data["uuid"])
        # then load the properties
        node.update_from_dict(data)
        return node

    def update_from_dict(self, data: Dict[str, Any]) -> None:
        """udpate node from dict data. Set metadata and properties.
        This method can be overrided.
        """
        from node_graph.utils import collect_values_inside_namespace

        for key in ["uuid", "state", "action", "description", "hash", "position"]:
            if data.get(key):
                setattr(self, key, data.get(key))
        # read all the metadata
        for key in [
            "parent",
            "parent_uuid",
        ]:
            if data["metadata"].get(key):
                setattr(self, key, data["metadata"].get(key))
        # properties first, because the socket may be dynamic
        for prop in data["properties"].values():
            self.properties[prop["name"]].value = prop["value"]
        # inputs
        input_values = collect_values_inside_namespace(data["inputs"])
        self.inputs._set_socket_value(input_values)

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
        executor: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Create a node from a identifier.
        When a plugin create a node, it should provide its own node pool.
        Then call super().new(identifier, name, NodePool) to create a node.
        """
        from node_graph.collection import get_item_class

        if NodePool is None:
            from node_graph.nodes import NodePool

        ItemClass = get_item_class(identifier, NodePool, Node)
        node = ItemClass(name=name, metadata=metadata, executor=executor)
        return node

    def copy(
        self,
        name: Optional[str] = None,
        parent: Optional[Any] = None,
    ) -> Any:
        """Copy a node.

        Copy a node to a new node. If parent is None, the node will be copied inside the same parent,
        otherwise the node will be copied to a new parent.
        The properties, inputs and outputs will be copied.

        Args:
            name (str, optional): _description_. Defaults to None.
            parent (NodeGraph, optional): _description_. Defaults to None.

        Returns:
            Node: _description_
        """
        if parent is not None:
            # copy node to a new parent, keep the name
            name = self.name if name is None else name
        else:
            # copy node inside the same parent, change the name
            parent = self.parent
            name = f"{self.name}_copy" if name is None else name
        node = self.__class__(name=name, uuid=None, parent=parent)
        # becareful when copy the properties, the value should be copied
        # it will update the sockets, so we copy the properties first
        # then overwrite the sockets
        for i in range(len(self.properties)):
            node.properties[i].value = self.properties[i].value
        node.inputs = self.inputs._copy(node=node)
        node.outputs = self.outputs._copy(node=node)
        return node

    def get_executor(self) -> Optional[NodeExecutor]:
        """Get the default executor."""
        return self._executor

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

    def set(self, data: Dict[str, Any]) -> None:
        """Set properties by a dict.

        Args:
            data (dict): _description_
        """

        data = deep_copy_only_dicts(data)
        for key, value in data.items():
            # if the value is a node, link the node's top-level output to the input
            if isinstance(value, Node):
                self.parent.add_link(value.outputs["_outputs"], self.inputs[key])
                continue
            if key in self.properties:
                self.properties[key].value = value
            elif key in self.inputs:
                self.inputs[key]._set_socket_value(value)
            elif self.inputs._socket_is_dynamic:
                # if the socket is dynamic, we can add the input dynamically
                inp = self.add_input(self.SocketPool.any, key)
                inp._set_socket_value(value)
            else:
                raise Exception(
                    "No property named {}. Accept name are {}".format(
                        key,
                        list(self.get_property_names() + list(self.get_input_names())),
                    )
                )

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

        tdata = self.to_dict()

        for key in ("properties", "executor", "node_class", "process"):
            tdata.pop(key, None)
        inputs = []
        for input in tdata["inputs"]["sockets"].values():
            input.pop("property", None)
            inputs.append(input)

        tdata["inputs"] = inputs

        tdata["label"] = tdata["identifier"]

        wgdata = {"name": self.name, "nodes": {self.name: tdata}, "links": []}
        return wgdata

    def _repr_mimebundle_(self, *args: Any, **kwargs: Any) -> any:
        # if ipywdigets > 8.0.0, use _repr_mimebundle_ instead of _ipython_display_
        self._widget.value = self.to_widget_value()
        if hasattr(self._widget, "_repr_mimebundle_"):
            return self._widget._repr_mimebundle_(*args, **kwargs)
        else:
            return self._widget._ipython_display_(*args, **kwargs)

    def to_html(self, output: str = None, **kwargs):
        """Write a standalone html file to visualize the task."""
        self._widget.value = self.to_widget_value()
        return self._widget.to_html(output=output, **kwargs)
