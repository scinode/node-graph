from uuid import uuid1
from node_graph.sockets import socket_pool
from node_graph.properties import property_pool
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
        list_index (int): Node id inside the node graph.
        parent_uuid (str): UUID of the node graph this node belongs to.
        platform (str): Platform that used to create this node.

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
    socket_pool = socket_pool
    property_pool = property_pool

    identifier: str = "Node"
    node_type: str = "Normal"
    list_index: int = 0
    parent_uuid: str = ""
    platform: str = "node_graph"
    catalog: str = "Node"
    group_properties: List[List[str]] = None
    group_inputs: List[List[str]] = None
    group_outputs: List[List[str]] = None
    is_dynamic: bool = False

    def __init__(
        self,
        list_index: int = 0,
        name: Optional[str] = None,
        uuid: Optional[str] = None,
        parent: Optional[Any] = None,
        metadata: Optional[Dict[str, Any]] = None,
        executor: Optional[NodeExecutor] = None,
        property_collection_class: Any = PropertyCollection,
        input_collection_class: Any = NodeSocketNamespace,
        output_collection_class: Any = NodeSocketNamespace,
        ctrl_input_collection_class: Any = NodeSocketNamespace,
        ctrl_output_collection_class: Any = NodeSocketNamespace,
    ) -> None:
        """Initialize the Node.

        Args:
            list_index (int, optional): Node id inside the node graph. Defaults to 0.
            name (str, optional): Name of the node. Defaults to None.
            uuid (str, optional): UUID of the node. Defaults to None.
            parent (Any, optional): Parent node. Defaults to None.
            property_collection_class (Any, optional): Property collection class. Defaults to PropertyCollection.
            input_collection_class (Any, optional): Input socket collection class. Defaults to InputSocketCollection.
            output_collection_class (Any, optional): Output socket collection class. Defaults to NodeSocketNamespace.
        """
        self.list_index = list_index
        self.name = name or "{}{}".format(self.identifier.split(".")[-1], list_index)
        self.uuid = uuid or str(uuid1())
        self.parent = parent
        self._metadata = metadata or {}
        self._executor = executor
        self.properties = property_collection_class(self, pool=self.property_pool)
        self.inputs = input_collection_class("inputs", node=self, pool=self.socket_pool)
        self.outputs = output_collection_class(
            "outputs", node=self, pool=self.socket_pool
        )
        self.ctrl_inputs = ctrl_input_collection_class(
            "ctrl_Inputs", node=self, pool=self.socket_pool
        )
        self.ctrl_outputs = ctrl_output_collection_class(
            "ctrl_outputs", node=self, pool=self.socket_pool
        )
        self.state = "CREATED"
        self.action = "NONE"
        self.position = [30 * self.list_index, 30 * self.list_index]
        self.description = ""
        self.log = ""
        self.ng = self.get_node_group() if self.node_type.upper() == "GROUP" else None
        self.create_properties()
        self.create_sockets()
        self.create_ctrl_sockets()
        self._widget = NodeGraphWidget(
            settings={"minmap": False},
            style={"width": "80%", "height": "600px"},
        )

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

    def add_ctrl_input(self, identifier: str, name: str, **kwargs) -> NodeSocket:
        input = self.ctrl_inputs._new(identifier, name, **kwargs)
        return input

    def add_ctrl_output(self, identifier: str, name: str, **kwargs) -> NodeSocket:
        output = self.ctrl_outputs._new(identifier, name, **kwargs)
        return output

    def get_input_names(self) -> List[str]:
        return self.inputs._get_keys()

    def get_output_names(self) -> List[str]:
        return self.outputs._get_keys()

    def get_property_names(self) -> List[str]:
        return self.properties._get_keys()

    def create_properties(self) -> None:
        """Create properties for this node.
        If this node is a group node, create properties based on the exposed properties.
        """
        self.properties._clear()
        if self.node_type.upper() == "GROUP":
            self.create_group_properties()

    def create_group_properties(self) -> None:
        """Create properties based on the exposed properties."""
        group_properties = self.group_properties if self.group_properties else []
        for prop in group_properties:
            node_prop, new_prop_name = prop
            node, prop_name = node_prop.split(".")
            if prop_name not in self.ng.nodes[node].get_property_names():
                raise ValueError(
                    "Property {} does not exist in the properties of node {}".format(
                        prop_name, node
                    )
                )
            p = self.ng.nodes[node].properties[prop_name].copy()
            p.name = new_prop_name
            # TODO add the default value to group property
            self.properties.append(p)

    def create_sockets(self) -> None:
        """Create input and output sockets for this node.
        If this node is a group node, create sockets based on group inputs and outputs.
        """
        self.inputs._clear()
        self.outputs._clear()
        if self.node_type.upper() == "GROUP":
            self.create_group_sockets()

    def create_ctrl_sockets(self) -> None:
        """Create control input and output sockets for this node."""
        self.ctrl_inputs._clear()
        self.ctrl_outputs._clear()
        socket = self.add_ctrl_input("node_graph.any", "entry")
        socket._link_limit = 1000
        socket = self.add_ctrl_input("node_graph.any", "ctrl")
        socket._link_limit = 1000
        socket = self.add_ctrl_output("node_graph.any", "exit")
        socket = self.add_ctrl_output("node_graph.any", "ctrl")
        socket._link_limit = 1000

    def create_group_sockets(self) -> None:
        """Create input and output sockets based on group inputs and outputs.

        group_inputs = [
            ["add1.x", "x"],
            ["add1.y", "y"]]
        """
        group_inputs = self.group_inputs if self.group_inputs else []
        for input in group_inputs:
            node_socket, name = input
            node, socket = node_socket.split(".")
            if socket not in self.ng.nodes[node].get_input_names():
                raise ValueError(
                    "Socket {} does not exist in the inputs of node {}".format(
                        socket, node
                    )
                )
            identifier = self.ng.nodes[node].inputs[socket].identifier
            self.add_input(identifier, name)
        group_outputs = self.group_outputs if self.group_outputs else []
        for output in group_outputs:
            node_socket, name = output
            node, socket = node_socket.split(".")
            if socket not in self.ng.nodes[node].get_output_names():
                raise ValueError(
                    "Socket {} does not exist in the outputs of node {}".format(
                        socket, node
                    )
                )
            identifier = self.ng.nodes[node].outputs[socket].identifier
            self.add_output(identifier, name)

    def reset(self) -> None:
        """Reset this node and all its child nodes to "CREATED"."""

    # @property
    # def group_properties(self) -> List[List[str]]:
    #     return self.ng.group_properties if self.ng else []

    # @property
    # def group_inputs(self) -> List[List[str]]:
    #     return self.ng.group_inputs if self.ng else []

    # @property
    # def group_outputs(self) -> List[List[str]]:
    #     return self.ng.group_outputs if self.ng else []

    @property
    def node_group(self) -> Any:
        return self.get_node_group()

    def get_node_group(self) -> Any:
        """Get the node group of this node.

        Returns:
            NodeGraph: The node group of this node.
        """
        return self.get_default_node_group()

    def get_default_node_group(self) -> Any:
        from node_graph import NodeGraph

        ng = NodeGraph(
            name=self.name,
            uuid=self.uuid,
        )
        return ng

    def to_dict(self, short: bool = False) -> Dict[str, Any]:
        """Save all datas, include properties, input and output sockets."""
        from node_graph.version import __version__

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
            input_sockets = self.export_input_sockets()
            output_sockets = self.export_output_sockets()
            ctrl_input_sockets = self.export_ctrl_input_sockets()
            ctrl_output_sockets = self.export_ctrl_output_sockets()
            executor = self.export_executor_to_dict()
            data = {
                "version": "node_graph@{}".format(__version__),
                "identifier": self.identifier,
                "uuid": self.uuid,
                "name": self.name,
                "list_index": self.list_index,
                "state": self.state,
                "action": self.action,
                "error": "",
                "metadata": metadata,
                "properties": properties,
                "inputs": input_sockets,
                "outputs": output_sockets,
                "ctrl_inputs": ctrl_input_sockets,
                "ctrl_outputs": ctrl_output_sockets,
                "executor": executor,
                "position": self.position,
                "description": self.description,
                "log": self.log,
                "hash": "",  # we can only calculate the hash during runtime when all the data is ready
            }
        data.update(self.get_args_data())
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
                "platform": self.platform,
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

    def export_input_sockets(self) -> List[Dict[str, Any]]:
        """Export input sockets to a dictionary."""
        # save all relations using links
        inputs = {}
        for input in self.inputs:
            inputs[input._name] = input._to_dict()
        return inputs

    def export_output_sockets(self) -> List[Dict[str, Any]]:
        """Export output sockets to a dictionary."""
        # save all relations using links
        outputs = {}
        for output in self.outputs:
            outputs[output._name] = output._to_dict()
        return outputs

    def export_ctrl_input_sockets(self) -> List[Dict[str, Any]]:
        """Export ctrl_input sockets to a dictionary."""
        # save all relations using links
        ctrl_inputs = {}
        for socket in self.ctrl_inputs:
            ctrl_inputs[socket._name] = socket._to_dict()
        return ctrl_inputs

    def export_ctrl_output_sockets(self) -> List[Dict[str, Any]]:
        """Export ctrl_output sockets to a dictionary."""
        # save all relations using links
        ctrl_outputs = {}
        for socket in self.ctrl_outputs:
            ctrl_outputs[socket._name] = socket._to_dict()
        return ctrl_outputs

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
        cls, data: Dict[str, Any], node_pool: Optional[Dict[str, Any]] = None
    ) -> Any:
        """Rebuild Node from dict data."""
        from node_graph.utils import create_node

        if node_pool is None:
            from node_graph.nodes import node_pool

        # first create the node instance
        if data.get("metadata", {}).get("is_dynamic", False):
            node_class = create_node(data)
        else:
            node_class = node_pool[data["identifier"].upper()]

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
        for input in data["inputs"].values():
            if "sockets" in input:
                input_values = collect_values_inside_namespace(input)
                self.inputs[input["name"]]._set_socket_value(input_values)
            if "property" in input:
                self.inputs[input["name"]].property.value = input["property"]["value"]
                if input["property"].get("default", None):
                    self.inputs[input["name"]].property.default = input["property"][
                        "default"
                    ]
        # print("inputs: ", data.get("inputs", None))
        for input in data.get("inputs", {}).values():
            self.inputs[input["name"]].uuid = input.get("uuid", None)
        # outputs
        # print("outputs: ", data.get("outputs", None))
        for output in data.get("outputs", {}).values():
            self.outputs[output["name"]].uuid = output.get("uuid", None)

    @classmethod
    def load(cls, uuid: str) -> None:
        """Load Node data from database."""

    @classmethod
    def new(
        cls,
        identifier: str,
        name: Optional[str] = None,
        node_pool: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        executor: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Create a node from a identifier.
        When a plugin create a node, it should provide its own node pool.
        Then call super().new(identifier, name, node_pool) to create a node.
        """
        from node_graph.utils import get_item_class

        if node_pool is None:
            from node_graph.nodes import node_pool

        ItemClass = get_item_class(identifier, node_pool, Node)
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
        node.inputs = self.inputs._copy(parent=node)
        node.outputs = self.outputs._copy(parent=node)
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
        for input in tdata["inputs"].values():
            input.pop("property", None)

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
