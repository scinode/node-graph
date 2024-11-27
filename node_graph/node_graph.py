from node_graph.collection import NodeCollection, LinkCollection
from uuid import uuid1
from node_graph.nodes import node_pool
from typing import Dict, Any, List, Optional, Union
from node_graph.version import __version__
import yaml
from node_graph.utils import yaml_to_dict, create_node


class NodeGraph:
    """A collection of nodes and links.

    Attributes:
        name (str): The name of the node graph.
        uuid (str): The UUID of this node graph.
        type (str): The type of the node graph.
        state (str): The state of this node graph.
        action (str): The action of this node graph.
        platform (str): The platform used to create this node graph.
        description (str): A description of the node graph.
        log (str): Log information for the node graph.
        group_properties (List[str]): Group properties of the node graph.
        group_inputs (List[str]): Group inputs of the node graph.
        group_outputs (List[str]): Group outputs of the node graph.

    Examples:
        >>> from node_graph import NodeGraph
        >>> ng = NodeGraph(name="my_first_nodegraph")

        Add nodes:
        >>> float1 = ng.nodes.new("node_graph.test_float", name="float1")
        >>> add1 = ng.nodes.new("node_graph.test_add", name="add1")

        Add links:
        >>> ng.links.new(float1.outputs[0], add1.inputs[0])

        Export to dict:
        >>> ng.to_dict()
    """

    node_pool: Dict[str, Any] = node_pool
    platform: str = "node_graph"

    def __init__(
        self,
        name: str = "NodeGraph",
        uuid: Optional[str] = None,
        type: str = "NORMAL",
    ) -> None:
        """Initializes a new instance of the NodeGraph class.

        Args:
            name (str, optional): The name of the node graph. Defaults to "NodeGraph".
            uuid (str, optional): The UUID of the node graph. Defaults to None.
            type (str, optional): The type of the node graph. Defaults to "NORMAL".
        """
        self.name: str = name
        self.uuid: str = uuid or str(uuid1())
        self.type: str = type
        self.nodes: NodeCollection = NodeCollection(self, pool=self.node_pool)
        self.links: LinkCollection = LinkCollection(self)
        self.ctrl_links: LinkCollection = LinkCollection(self)
        self.state: str = "CREATED"
        self.action: str = "NONE"
        self.description: str = ""
        self.log: str = ""
        self.group_properties: List[str] = []
        self.group_inputs: List[str] = []
        self.group_outputs: List[str] = []

    def launch(self) -> None:
        """Launches the node graph."""
        raise NotImplementedError("The 'launch' method is not implemented.")

    def save(self) -> None:
        """Saves the node graph to the database."""
        raise NotImplementedError("The 'save' method is not implemented.")

    def to_dict(self, short: bool = False) -> Dict[str, Any]:
        """Converts the node graph to a dictionary.

        Args:
            short (bool, optional): Indicates whether to include short node representations. Defaults to False.

        Returns:
            Dict[str, Any]: The node graph data.
        """
        metadata: Dict[str, Any] = self.get_metadata()
        nodes: Dict[str, Any] = self.nodes_to_dict(short=short)
        links: List[Dict[str, Any]] = self.links_to_dict()
        ctrl_links: List[Dict[str, Any]] = self.ctrl_links_to_dict()
        data: Dict[str, Any] = {
            "version": f"node_graph@{__version__}",
            "uuid": self.uuid,
            "name": self.name,
            "state": self.state,
            "action": self.action,
            "error": "",
            "metadata": metadata,
            "nodes": nodes,
            "links": links,
            "ctrl_links": ctrl_links,
            "description": self.description,
            "log": self.log,
        }
        return data

    def get_metadata(self) -> Dict[str, Any]:
        """Converts the metadata to a dictionary.

        Returns:
            Dict[str, Any]: The metadata.
        """
        metadata: Dict[str, Any] = {
            "type": self.type,
            "platform": self.platform,
            "group_properties": self.group_properties,
            "group_inputs": self.group_inputs,
            "group_outputs": self.group_outputs,
        }
        return metadata

    def nodes_to_dict(self, short: bool = False) -> Dict[str, Any]:
        """Converts the nodes to a dictionary.

        Args:
            short (bool, optional): Indicates whether to include short node representations. Defaults to False.

        Returns:
            Dict[str, Any]: The nodes data.
        """
        nodes: Dict[str, Any] = {}
        for node in self.nodes:
            nodes[node.name] = node.to_dict(short=short)
        return nodes

    def links_to_dict(self) -> List[Dict[str, Any]]:
        """Converts the links to a list of dictionaries.

        Returns:
            List[Dict[str, Any]]: The links data.
        """
        links: List[Dict[str, Any]] = [link.to_dict() for link in self.links]
        return links

    def ctrl_links_to_dict(self) -> List[Dict[str, Any]]:
        """Converts the control links to a list of dictionaries.

        Returns:
            List[Dict[str, Any]]: The control links data.
        """
        ctrl_links: List[Dict[str, Any]] = [link.to_dict() for link in self.ctrl_links]
        return ctrl_links

    def to_yaml(self) -> str:
        """Exports the node graph to a YAML format data.

        Results of the nodes are not exported.

        Returns:
            str: The YAML string representation of the node graph.
        """
        data: Dict[str, Any] = self.to_dict()
        for node in data["nodes"].values():
            node.pop("results", None)
        return yaml.dump(data, sort_keys=False)

    def update(self) -> None:
        """Updates the node graph."""
        raise NotImplementedError("The 'update' method is not implemented.")

    def update_nodes(self, data: Dict[str, Any]) -> None:
        """Updates the nodes in the node graph.

        Args:
            data (Dict[str, Any]): The updated node data.
        """
        for node in self.nodes:
            node_data = data.get(node.name)
            if node_data:
                node.state = node_data.get("state", node.state)
                node.counter = node_data.get("counter", node.counter)
                node.action = node_data.get("action", node.action)
                node.update()
            else:
                # Handle the case where node data is missing
                pass

    @classmethod
    def from_dict(cls, ngdata: Dict[str, Any]) -> "NodeGraph":
        """Rebuilds a node graph from a dictionary.

        Args:
            ngdata (Dict[str, Any]): The data of the node graph.

        Returns:
            NodeGraph: The rebuilt node graph.
        """
        ng: "NodeGraph" = cls(
            name=ngdata["name"],
            uuid=ngdata.get("uuid"),
            type=ngdata["metadata"].get("type", "NORMAL"),
        )
        for key in ["state", "action", "description", "log"]:
            if ngdata.get(key):
                setattr(ng, key, ngdata.get(key))
        for key in ["group_properties", "group_inputs", "group_outputs"]:
            if ngdata["metadata"].get(key):
                setattr(ng, key, ngdata["metadata"].get(key))
        for name, ndata in ngdata["nodes"].items():
            if ndata.get("metadata", {}).get("is_dynamic", False):
                identifier = create_node(ndata)
            else:
                identifier = ndata["identifier"]
            node = ng.nodes.new(
                identifier,
                name=name,
                uuid=ndata.pop("uuid", None),
            )
            node.update_from_dict(ndata)
        for link in ngdata.get("links", []):
            ng.links.new(
                ng.nodes[link["from_node"]].outputs[link["from_socket"]],
                ng.nodes[link["to_node"]].inputs[link["to_socket"]],
            )
        for link in ngdata.get("ctrl_links", []):
            ng.ctrl_links.new(
                ng.nodes[link["from_node"]].ctrl_outputs[link["from_socket"]],
                ng.nodes[link["to_node"]].ctrl_inputs[link["to_socket"]],
            )
        return ng

    @classmethod
    def from_yaml(
        cls, filename: Optional[str] = None, string: Optional[str] = None
    ) -> "NodeGraph":
        """Builds a node graph from a YAML file or string.

        Args:
            filename (str, optional): The filename of the YAML file. Defaults to None.
            string (str, optional): The YAML string. Defaults to None.

        Raises:
            ValueError: If neither filename nor string is provided.

        Returns:
            NodeGraph: The built node graph.
        """
        if filename:
            with open(filename, "r") as f:
                ngdata = yaml.safe_load(f)
        elif string:
            ngdata = yaml.safe_load(string)
        else:
            raise ValueError("Please specify a filename or YAML string.")
        ngdata = yaml_to_dict(ngdata)
        ng = cls.from_dict(ngdata)
        return ng

    def copy(self, name: Optional[str] = None) -> "NodeGraph":
        """Copies the node graph.

        The nodes and links are copied.

        Args:
            name (str, optional): The name of the new node graph. Defaults to None.

        Returns:
            NodeGraph: The copied node graph.
        """
        name = f"{self.name}_copy" if name is None else name
        ng: "NodeGraph" = self.__class__(name=name, uuid=None)
        ng.nodes = self.nodes.copy(parent=ng)
        for link in self.links:
            ng.links.new(
                ng.nodes[link.from_node.name].outputs[link.from_socket.name],
                ng.nodes[link.to_node.name].inputs[link.to_socket.name],
            )
        return ng

    def copy_using_dict(self) -> "NodeGraph":
        """Copies the node graph using dictionary data.

        First exports the node graph to dictionary data.
        Then resets the UUID of the node graph and nodes.
        Finally, rebuilds the node graph from the dictionary data.

        Returns:
            NodeGraph: The copied node graph.
        """
        ngdata: Dict[str, Any] = self.to_dict()
        ngdata["uuid"] = str(uuid1())
        for node_data in ngdata["nodes"].values():
            node_data["uuid"] = str(uuid1())
        ng: "NodeGraph" = self.from_dict(ngdata)
        return ng

    @classmethod
    def load(cls, uuid: str) -> None:
        """Loads data from the database."""
        raise NotImplementedError("The 'load' method is not implemented.")

    def copy_subset(
        self, node_list: List[str], name: Optional[str] = None, add_ref: bool = True
    ) -> "NodeGraph":
        """Copies a subset of the node graph.

        Args:
            node_list (List[str]): The names of the nodes to be copied.
            name (str, optional): The name of the new node graph. Defaults to None.
            add_ref (bool, optional): Indicates whether to add reference nodes. Defaults to True.

        Returns:
            NodeGraph: The new node graph.
        """
        ng: "NodeGraph" = self.__class__(name=name, uuid=None)
        for node_name in node_list:
            ng.nodes.append(self.nodes[node_name].copy(nodegraph=ng))
        for link in self.links:
            if (
                add_ref
                and link.from_node.name not in ng.nodes.keys()
                and link.to_node.name in ng.nodes.keys()
            ):
                ng.nodes.append(
                    self.nodes[link.from_node.name].copy(nodegraph=ng, is_ref=True)
                )
            if (
                link.from_node.name in ng.nodes.keys()
                and link.to_node.name in ng.nodes.keys()
            ):
                ng.links.new(
                    ng.nodes[link.from_node.name].outputs[link.from_socket.name],
                    ng.nodes[link.to_node.name].inputs[link.to_socket.name],
                )
        return ng

    def __getitem__(self, key: Union[str, List[str]]) -> "NodeGraph":
        """Gets a sub-nodegraph by the name(s) of nodes.

        Args:
            key (Union[str, List[str]]): The name(s) of the node(s).

        Returns:
            NodeGraph: The sub-nodegraph.
        """
        if isinstance(key, str):
            keys = [key]
        elif isinstance(key, list):
            keys = key
        else:
            raise TypeError("Key must be a string or list of strings.")
        ng = self.copy_subset(keys)
        return ng

    def __iadd__(self, other: "NodeGraph") -> "NodeGraph":
        """Adds another node graph to this node graph.

        Args:
            other (NodeGraph): The other node graph to add.

        Returns:
            NodeGraph: The combined node graph.
        """
        self.nodes.extend(other.nodes.copy(parent=self))
        for link in other.links:
            self.links.new(
                self.nodes[link.from_node.name].outputs[link.from_socket.name],
                self.nodes[link.to_node.name].inputs[link.to_socket.name],
            )
        return self

    def __add__(self, other: "NodeGraph") -> "NodeGraph":
        """Returns a new node graph that is the combination of this and another.

        Args:
            other (NodeGraph): The other node graph to add.

        Returns:
            NodeGraph: The combined node graph.
        """
        new_graph = self.copy()
        new_graph += other
        return new_graph

    def delete_nodes(self, node_list: List[str]) -> None:
        """Deletes nodes from the node graph.

        Args:
            node_list (List[str]): The names of the nodes to delete.
        """
        for name in node_list:
            if name not in self.nodes.keys():
                raise ValueError(f"Node '{name}' not found in the node graph.")
            link_indices: List[int] = []
            for index, link in enumerate(self.links):
                if link.from_node.name == name or link.to_node.name == name:
                    link_indices.append(index)
            # Delete links in reverse order to avoid index shift
            for index in sorted(link_indices, reverse=True):
                del self.links[index]
            self.nodes.delete(name)

    def wait(self) -> None:
        """Waits for the node graph to finish.

        Args:
            timeout (int, optional): The maximum time to wait in seconds. Defaults to 50.
        """
        return NotImplementedError("The 'wait' method is not implemented.")

    def __repr__(self) -> str:
        return f'NodeGraph(name="{self.name}", uuid="{self.uuid}")'
