from uuid import uuid1
from node_graph.sockets import socket_pool
from node_graph.properties import property_pool
from typing import List, Optional, Dict, Any, Union
import json
import hashlib
import cloudpickle as pickle
from node_graph.utils import deep_copy_only_dicts
from node_graph.socket import NodeSocket

from node_graph.collection import (
    PropertyCollection,
    InputSocketCollection,
    OutputSocketCollection,
)


class Node:
    """Base class for Node.

    Attributes:
        identifier (str): The identifier is used for loading the Node.
        node_type (str): Type of this node. Possible values are "Normal", "REF", "GROUP".
        inner_id (int): Node id inside the node graph.
        parent_uuid (str): UUID of the node graph this node belongs to.
        args (list): Positional arguments of the executor.
        kwargs (list): Keyword arguments of the executor.
        var_args (str): Variable arguments of the executor.
        var_kwargs (str): Variable keyword arguments of the executor.
        platform (str): Platform that used to create this node.

    Examples:
        Add nodes:
        >>> float1 = nt.nodes.new("TestFloat", name="float1")
        >>> add1 = nt.nodes.new("TestDelayAdd", name="add1")

        Copy node:
        >>> n = node.copy(name="new_name")

        Append node to node graph:
        >>> nt.nodes.append(node)

    """

    # This is the entry point for the socket and property pool
    socket_pool = socket_pool
    property_pool = property_pool

    identifier: str = "Node"
    node_type: str = "Normal"
    inner_id: int = 0
    parent_uuid: str = ""
    platform: str = "node_graph"
    catalog: str = "Node"
    args: List[Any] = []
    kwargs: List[Any] = []
    var_args: Optional[str] = None
    var_kwargs: Optional[str] = None
    group_inputs: List[List[str]] = []
    group_outputs: List[List[str]] = []

    def __init__(
        self,
        inner_id: int = 0,
        name: Optional[str] = None,
        uuid: Optional[str] = None,
        parent: Optional[Any] = None,
        property_collection_class: Any = PropertyCollection,
        input_collection_class: Any = InputSocketCollection,
        output_collection_class: Any = OutputSocketCollection,
    ) -> None:
        """Initialize the Node.

        Args:
            inner_id (int, optional): Node id inside the node graph. Defaults to 0.
            name (str, optional): Name of the node. Defaults to None.
            uuid (str, optional): UUID of the node. Defaults to None.
            parent (Any, optional): Parent node. Defaults to None.
            property_collection_class (Any, optional): Property collection class. Defaults to PropertyCollection.
            input_collection_class (Any, optional): Input socket collection class. Defaults to InputSocketCollection.
            output_collection_class (Any, optional): Output socket collection class. Defaults to OutputSocketCollection.
        """
        self.inner_id = inner_id
        self.name = name or "{}{}".format(self.identifier.split(".")[-1], inner_id)
        self.uuid = uuid or str(uuid1())
        self.parent = parent
        self.properties = property_collection_class(self, pool=self.property_pool)
        self.inputs = input_collection_class(self, pool=self.socket_pool)
        self.outputs = output_collection_class(self, pool=self.socket_pool)
        self.ctrl_inputs = InputSocketCollection(self, pool=self.socket_pool)
        self.ctrl_outputs = OutputSocketCollection(self, pool=self.socket_pool)
        self.executor = None
        self.state = "CREATED"
        self.action = "NONE"
        self.position = [30 * self.inner_id, 30 * self.inner_id]
        self.description = ""
        self.log = ""
        self.ng = self.get_node_group() if self.node_type.upper() == "GROUP" else None
        self.create_properties()
        self.create_sockets()
        self.create_ctrl_sockets()

    def create_properties(self) -> None:
        """Create properties for this node.
        If this node is a group node, create properties based on the exposed properties.
        """
        self.properties.clear()
        if self.node_type.upper() == "GROUP":
            self.create_group_properties()

    def create_group_properties(self) -> None:
        """Create properties based on the exposed properties."""
        for prop in self.group_properties:
            node_prop, new_prop_name = prop
            node, prop_name = node_prop.split(".")
            if prop_name not in self.ng.nodes[node].properties.keys():
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
        self.inputs.clear()
        self.outputs.clear()
        if self.node_type.upper() == "GROUP":
            self.create_group_sockets()

    def create_ctrl_sockets(self) -> None:
        """Create control input and output sockets for this node."""
        self.ctrl_inputs.clear()
        self.ctrl_outputs.clear()
        socket = self.ctrl_inputs.new("node_graph.any", "entry")
        socket.link_limit = 1000
        socket = self.ctrl_inputs.new("node_graph.any", "ctrl")
        socket.link_limit = 1000
        socket = self.ctrl_outputs.new("node_graph.any", "exit")
        socket = self.ctrl_outputs.new("node_graph.any", "ctrl")
        socket.link_limit = 1000

    def create_group_sockets(self) -> None:
        """Create input and output sockets based on group inputs and outputs.

        group_inputs = [
            ["add1.x", "x"],
            ["add1.y", "y"]]
        """
        for input in self.group_inputs:
            node_socket, name = input
            node, socket = node_socket.split(".")
            if socket not in self.ng.nodes[node].inputs.keys():
                raise ValueError(
                    "Socket {} does not exist in the inputs of node {}".format(
                        socket, node
                    )
                )
            identifier = self.ng.nodes[node].inputs[socket].identifier
            self.inputs.new(identifier, name)
        for output in self.group_outputs:
            node_socket, name = output
            node, socket = node_socket.split(".")
            if socket not in self.ng.nodes[node].outputs.keys():
                raise ValueError(
                    "Socket {} does not exist in the outputs of node {}".format(
                        socket, node
                    )
                )
            identifier = self.ng.nodes[node].outputs[socket].identifier
            self.outputs.new(identifier, name)

    def reset(self) -> None:
        """Reset this node and all its child nodes to "CREATED"."""

    @property
    def group_properties(self) -> List[List[str]]:
        return self.ng.group_properties if self.ng else []

    @property
    def group_inputs(self) -> List[List[str]]:
        return self.ng.group_inputs if self.ng else []

    @property
    def group_outputs(self) -> List[List[str]]:
        return self.ng.group_outputs if self.ng else []

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

        nt = NodeGraph(
            name=self.name,
            uuid=self.uuid,
        )
        return nt

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
            properties = self.properties_to_dict()
            input_sockets = self.input_sockets_to_dict()
            output_sockets = self.output_sockets_to_dict()
            ctrl_input_sockets = self.ctrl_input_sockets_to_dict()
            ctrl_output_sockets = self.ctrl_output_sockets_to_dict()
            executor = self.executor_to_dict()
            data = {
                "version": "node_graph@{}".format(__version__),
                "uuid": self.uuid,
                "name": self.name,
                "inner_id": self.inner_id,
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
                "hash": "",
                "node_class": pickle.dumps(""),
            }
            # calculate the hash of metadata
            hash_metadata = {
                "executor": executor,
                "args": self.args,
                "kwargs": self.kwargs,
                "var_args": self.var_args,
                "var_kwargs": self.var_kwargs,
            }
            # we can not hash binary data for the moment
            if not executor.get("is_pickle", False):
                data["metadata"]["hash"] = hashlib.md5(
                    json.dumps(hash_metadata).encode("utf-8")
                ).hexdigest()
            else:
                data["metadata"]["hash"] = str(uuid1())
                # we pickle the class so that we can load again
                data["node_class"] = pickle.dumps(self.__class__)
        # to avoid some dict has the same address with others nodes
        # which happens when {} is used as default value
        # we copy the value only
        data = deep_copy_only_dicts(data)
        return data

    def get_metadata(self) -> Dict[str, Any]:
        """Export metadata to a dictionary."""
        metadata = {
            "node_type": self.node_type,
            "catalog": self.catalog,
            "identifier": self.identifier,
            "parent_uuid": self.parent.uuid if self.parent else self.parent_uuid,
            "platform": self.platform,
            "args": self.args,
            "kwargs": self.kwargs,
            "var_args": self.var_args,
            "var_kwargs": self.var_kwargs,
            "group_properties": self.group_properties,
            "group_inputs": self.group_inputs,
            "group_outputs": self.group_outputs,
        }
        return metadata

    def properties_to_dict(self) -> Dict[str, Any]:
        """Export properties to a dictionary.
        This data will be used for calculation.
        """
        properties = {}
        for p in self.properties:
            properties[p.name] = p.to_dict()
        # properties from inputs
        # data from property
        for input in self.inputs:
            if input.property is not None:
                properties[input.name] = input.property.to_dict()
            else:
                properties[input.name] = None
        return properties

    def input_sockets_to_dict(self) -> List[Dict[str, Any]]:
        """Export input sockets to a dictionary."""
        # save all relations using links
        inputs = []
        for socket in self.inputs:
            inputs.append(socket.to_dict())
        return inputs

    def output_sockets_to_dict(self) -> List[Dict[str, Any]]:
        """Export output sockets to a dictionary."""
        # save all relations using links
        outputs = []
        for socket in self.outputs:
            outputs.append(socket.to_dict())
        return outputs

    def ctrl_input_sockets_to_dict(self) -> List[Dict[str, Any]]:
        """Export ctrl_input sockets to a dictionary."""
        # save all relations using links
        ctrl_inputs = []
        for socket in self.ctrl_inputs:
            ctrl_inputs.append(socket.to_dict())
        return ctrl_inputs

    def ctrl_output_sockets_to_dict(self) -> List[Dict[str, Any]]:
        """Export ctrl_output sockets to a dictionary."""
        # save all relations using links
        ctrl_outputs = []
        for socket in self.ctrl_outputs:
            ctrl_outputs.append(socket.to_dict())
        return ctrl_outputs

    def executor_to_dict(self) -> Optional[Dict[str, Union[str, bool]]]:
        """Export executor dictionary to a dictionary.
        Three kinds of executor:
        - Python built-in function. e.g. getattr
        - User defined function
        - User defined class.
        """
        executor = self.get_executor() or self.executor
        if executor is None:
            return executor
        executor.setdefault("type", "function")
        executor.setdefault("is_pickle", False)
        if not executor["is_pickle"] and "name" not in executor:
            executor["name"] = executor["path"].split(".")[-1]
            executor["path"] = executor["path"][0 : -(len(executor["name"]) + 1)]
        return executor

    @classmethod
    def from_dict(
        cls, data: Dict[str, Any], node_pool: Optional[Dict[str, Any]] = None
    ) -> Any:
        """Rebuild Node from dict data."""

        if node_pool is None:
            from node_graph.nodes import node_pool

        # first create the node instance
        if data.get("executor", {}).get("is_pickle", False):
            node_class = pickle.loads(data["node_class"])
        else:
            node_class = node_pool[data["metadata"]["identifier"]]

        node = node_class(name=data["name"], uuid=data["uuid"])
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
        # read all the metadata
        for key in [
            "parent",
            "parent_uuid",
        ]:
            if data["metadata"].get(key):
                setattr(self, key, data["metadata"].get(key))
        # properties first, because the socket may be dynamic
        for name in self.properties.keys():
            if name in data["properties"]:
                self.properties[name].value = data["properties"][name]["value"]
        # inputs
        for name in self.inputs.keys():
            if name in data["properties"]:
                self.inputs[name].property.value = data["properties"][name]["value"]
        # print("inputs: ", data.get("inputs", None))
        if data.get("inputs", None):
            for i in range(len(data["inputs"])):
                if data["inputs"][i].get("uuid", None):
                    self.inputs[i].uuid = data["inputs"][i]["uuid"]
        # outputs
        # print("outputs: ", data.get("outputs", None))
        if data.get("outputs", None):
            for i in range(len(data["outputs"])):
                if data["outputs"][i].get("uuid", None):
                    self.outputs[i].uuid = data["outputs"][i]["uuid"]

    @classmethod
    def load(cls, uuid: str) -> None:
        """Load Node data from database."""

    @classmethod
    def new(
        cls,
        identifier: str,
        name: Optional[str] = None,
        node_pool: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Create a node from a identifier.
        When a plugin create a node, it should provide its own node pool.
        Then call super().new(identifier, name, node_pool) to create a node.
        """
        if node_pool is None:
            from node_graph.nodes import node_pool

        ItemClass = node_pool[identifier.upper()]
        node = ItemClass(name=name)
        return node

    def copy(
        self,
        name: Optional[str] = None,
        parent: Optional[Any] = None,
        is_ref: bool = False,
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
        print(f"Copy node {self.name}, as a ref: {is_ref}")
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
        node.inputs = self.inputs.copy(parent=node, is_ref=is_ref)
        node.outputs = self.outputs.copy(parent=node, is_ref=is_ref)
        return node

    def get_executor(self) -> Optional[Dict[str, Union[str, bool]]]:
        """Get the default executor."""
        executor = {"path": "", "name": ""}
        return executor

    def get_results(self) -> None:
        """Item data from database"""

    def update(self) -> None:
        """Update node state."""

    @property
    def results(self) -> None:
        return self.get_results()

    def __repr__(self) -> str:
        s = ""
        s += '{}(name="{}", properties = ['.format(self.__class__.__name__, self.name)
        s += ", ".join([f'"{x}"' for x in self.properties.keys()])
        s += "], inputs = ["
        s += ", ".join([f'"{x}"' for x in self.inputs.keys()])
        s += "], outputs = ["
        s += ", ".join([f'"{x}"' for x in self.outputs.keys()])
        s += "])\n"
        return s

    def set(self, data: Dict[str, Any]) -> None:
        """Set properties by a dict.

        Args:
            data (dict): _description_
        """

        data = deep_copy_only_dicts(data)
        for key, value in data.items():
            if key in self.properties.keys():
                self.properties[key].value = value
            elif key in self.inputs.keys():
                if isinstance(value, NodeSocket):
                    self.parent.links.new(value, self.inputs[key])
                else:
                    self.inputs[key].property.value = value
            else:
                raise Exception(
                    "No property named {}. Accept name are {}".format(
                        key, list(self.properties.keys() + list(self.inputs.keys()))
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
