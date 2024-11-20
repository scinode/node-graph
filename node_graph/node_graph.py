from node_graph.collection import NodeCollection, LinkCollection
from uuid import uuid1
from node_graph.nodes import node_pool
from typing import Dict, Any, List, Optional
from node_graph.version import __version__
import yaml
from node_graph.utils import yaml_to_dict
import time


class NodeGraph:
    """A collection of nodes and links.

    Attributes:
        uuid (str): The UUID of this node graph.
        state (str): The state of this node graph.
        action (str): The action of this node graph.
        platform (str): The platform used to create this node graph.

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

    # This is the entry point of the nodes
    node_pool: Dict[str, Any] = node_pool

    platform: str = "node_graph"
    uuid: str = ""
    type: str = "NORMAL"
    group_properties: List[str] = []
    group_inputs: List[str] = []
    group_outputs: List[str] = []

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

    def launch(self) -> None:
        """Launches the node graph."""

    def save(self) -> None:
        """Saves the node graph to the database."""

    def to_dict(self, short: bool = False) -> Dict[str, Any]:
        """Converts the node graph to a dictionary.

        Args:
            short (bool, optional): Indicates whether to include short node representations. Defaults to False.

        Returns:
            dict: The node graph data.
        """

        metadata: Dict[str, Any] = self.get_metadata()
        nodes: Dict[str, Any] = self.nodes_to_dict(short=short)
        links: List[Dict[str, Any]] = self.links_to_dict()
        ctrl_links: List[Dict[str, Any]] = self.ctrl_links_to_dict()
        data: Dict[str, Any] = {
            "version": "node_graph@{}".format(__version__),
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
            dict: The metadata.
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
            dict: The nodes data.
        """
        nodes: Dict[str, Any] = {}
        for node in self.nodes:
            if short:
                nodes[node.name] = node.to_dict(short=short)
            else:
                nodes[node.name] = node.to_dict()
        return nodes

    def links_to_dict(self) -> List[Dict[str, Any]]:
        """Converts the links to a list of dictionaries.

        Returns:
            list: The links data.
        """
        links: List[Dict[str, Any]] = []
        for link in self.links:
            links.append(link.to_dict())
        return links

    def ctrl_links_to_dict(self) -> List[Dict[str, Any]]:
        """Converts the control links to a list of dictionaries.

        Returns:
            list: The control links data.
        """
        ctrl_links: List[Dict[str, Any]] = []
        for link in self.ctrl_links:
            ctrl_links.append(link.to_dict())
        return ctrl_links

    def to_yaml(self) -> str:
        """Exports the node graph to a YAML format data.

        Results of the nodes are not exported.

        Returns:
            str: The YAML string representation of the node graph.
        """
        data: Dict[str, Any] = self.to_dict()
        for name, node in data["nodes"].items():
            node.pop("results", None)
        s: str = yaml.dump(data, sort_keys=False)
        return s

    def update(self) -> None:
        """Updates the node graph."""

    def update_nodes(self, data: Dict[str, Any]) -> None:
        """Updates the nodes in the node graph.

        Args:
            data (dict): The updated node data.
        """
        for node in self.nodes:
            node.state = data[node.name]["state"]
            node.counter = data[node.name]["counter"]
            node.action = data[node.name]["action"]
            node.update()

    @classmethod
    def from_dict(cls, ntdata: Dict[str, Any]) -> "NodeGraph":
        """Rebuilds a node graph from a dictionary.

        Args:
            ntdata (dict): The data of the node graph.

        Returns:
            NodeGraph: The rebuilt node graph.
        """
        from node_graph.utils import create_node

        ng: "NodeGraph" = cls(
            name=ntdata["name"],
            uuid=ntdata.get("uuid"),
        )
        for key in ["state", "action", "description"]:
            if ntdata.get(key):
                setattr(ng, key, ntdata.get(key))
        for key in [
            "group_properties",
            "group_inputs",
            "group_outputs",
        ]:
            if ntdata["metadata"].get(key):
                setattr(ng, key, ntdata["metadata"].get(key))
        for name, ndata in ntdata["nodes"].items():
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
        for link in ntdata.get("links", []):
            ng.links.new(
                ng.nodes[link["from_node"]].outputs[link["from_socket"]],
                ng.nodes[link["to_node"]].inputs[link["to_socket"]],
            )
        for link in ntdata.get("ctrl_links", []):
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

        Returns:
            NodeGraph: The built node graph.
        """
        if filename:
            with open(filename, "r") as f:
                ntdata = yaml.safe_load(f)
        elif string:
            ntdata = yaml.safe_load(string)
        else:
            raise Exception("Please specify a filename or YAML string.")
        ntdata = yaml_to_dict(ntdata)
        ng = cls.from_dict(ntdata)
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
        ng.nodes = self.nodes.copy(parent=nt)
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
        ntdata: Dict[str, Any] = self.to_dict()
        ntdata["uuid"] = str(uuid1())
        for name, node in ntdata["nodes"].items():
            node["uuid"] = str(uuid1())
        nodegraph: "NodeGraph" = self.from_dict(ntdata)
        return nodegraph

    @classmethod
    def load(cls, uuid: str) -> None:
        """Loads data from the database."""

    def copy_subset(
        self, node_list: List[str], name: Optional[str] = None, add_ref: bool = True
    ) -> "NodeGraph":
        """Copies a subset of the node graph.

        Args:
            node_list (list of str): The names of the nodes to be copied.
            name (str, optional): The name of the new node graph. Defaults to None.
            add_ref (bool, optional): Indicates whether to add reference nodes. Defaults to True.

        Returns:
            NodeGraph: The new node graph.
        """
        ng: "NodeGraph" = self.__class__(name=name, uuid=None)
        for node in node_list:
            ng.nodes.append(self.nodes[node].copy(nodegraph=nt))
        for link in self.links:
            if (
                add_ref
                and link.from_node.name not in ng.nodes.keys()
                and link.to_node.name in ng.nodes.keys()
            ):
                ng.nodes.append(
                    self.nodes[link.from_node.name].copy(nodegraph=nt, is_ref=True)
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

    def __getitem__(self, keys: List[str]) -> "NodeGraph":
        """Gets a sub-nodegraph by the names of nodes.

        Args:
            keys (list of str): The names of the nodes.

        Returns:
            NodeGraph: The sub-nodegraph.
        """
        ng: "NodeGraph" = self.copy_subset(keys)
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
        """Adds another node graph to this node graph.

        Args:
            other (NodeGraph): The other node graph to add.

        Returns:
            NodeGraph: The combined node graph.
        """
        self += other
        return self

    def delete_nodes(self, node_list: List[str]) -> None:
        """Deletes nodes from the node graph.

        Args:
            node_list (list of str): The names of the nodes to delete.
        """
        for name in node_list:
            link_index: List[int] = []
            for index, link in enumerate(self.links):
                if link.from_node.name == name or link.to_node.name == name:
                    link_index.append(index)
            del self.links[link_index]
            self.nodes.delete(name)

    def wait(self, timeout: int = 50) -> None:
        """Waits for the node graph to finish.

        Args:
            timeout (int, optional): The maximum time to wait in seconds. Defaults to 50.
        """
        start: float = time.time()
        self.update()
        while self.state not in ("PAUSED", "FINISHED", "FAILED", "CANCELLED"):
            time.sleep(0.5)
            self.update()
            if time.time() - start > timeout:
                return

    def __repr__(self) -> str:
        s: str = ""
        s += 'NodeGraph(name="{}, uuid="{}")\n'.format(self.name, self.uuid)
        return s
