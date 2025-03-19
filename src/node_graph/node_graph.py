from __future__ import annotations

from node_graph.collection import NodeCollection, LinkCollection
from uuid import uuid1
from node_graph.nodes import NodePool
from typing import Dict, Any, List, Optional, Union, Callable
import yaml
from node_graph.node import Node
from node_graph.socket import NodeSocket
from node_graph.link import NodeLink
from node_graph.utils import yaml_to_dict
from node_graph_widget import NodeGraphWidget


class NodeGraph:
    """A collection of nodes and links.

    Attributes:
        name (str): The name of the node graph.
        uuid (str): The UUID of this node graph.
        graph_type (str): The type of the node graph.
        state (str): The state of this node graph.
        action (str): The action of this node graph.
        platform (str): The platform used to create this node graph.
        description (str): A description of the node graph.
        group_properties (List[str]): Group properties of the node graph.
        group_inputs (List[str]): Group inputs of the node graph.
        group_outputs (List[str]): Group outputs of the node graph.

    Examples:
        >>> from node_graph import NodeGraph
        >>> ng = NodeGraph(name="my_first_nodegraph")

        Add nodes:
        >>> float1 = ng.add_node("node_graph.test_float", name="float1")
        >>> add1 = ng.add_node("node_graph.test_add", name="add1")

        Add links:
        >>> ng.add_link(float1.outputs[0], add1.inputs[0])

        Export to dict:
        >>> ng.to_dict()
    """

    NodePool: Dict[str, Any] = NodePool
    platform: str = "node_graph"

    def __init__(
        self,
        name: str = "NodeGraph",
        uuid: Optional[str] = None,
        graph_type: str = "NORMAL",
        state: str = "CREATED",
        action: str = "NONE",
        description: str = "",
        group_properties: List[dict] = None,
        group_inputs: List[dict] = None,
        group_outputs: List[dict] = None,
    ) -> None:
        """Initializes a new instance of the NodeGraph class.

        Args:
            name (str, optional): The name of the node graph. Defaults to "NodeGraph".
            uuid (str, optional): The UUID of the node graph. Defaults to None.
            graph_type (str, optional): The type of the node graph. Defaults to "NORMAL".
        """
        self.name = name
        self.uuid = uuid or str(uuid1())
        self.graph_type = graph_type
        self.nodes = NodeCollection(self, pool=self.NodePool)
        self.links = LinkCollection(self)
        self.state = state
        self.action = action
        self.description = description
        self.group_properties = group_properties or []
        self.group_inputs = group_inputs or []
        self.group_outputs = group_outputs or []
        self._widget = NodeGraphWidget(parent=self)
        self._version = 0  # keep track the changes

    @property
    def platform_version(self) -> str:
        """Retrieve the platform version dynamically from the package where Graph is implemented."""
        import importlib.metadata

        try:
            package_name = self.platform.replace("-", "_")
            return importlib.metadata.version(package_name)
        except importlib.metadata.PackageNotFoundError:
            return "unknown"

    def add_node(
        self, identifier: Union[str, Callable], name: str = None, **kwargs
    ) -> Node:
        """Adds a node to the node graph."""

        from node_graph.decorator import build_node_from_callable
        from node_graph.nodes.factory.nodegraph_node import NodeGraphNodeFactory

        if isinstance(identifier, NodeGraph):
            identifier = NodeGraphNodeFactory.create_node(identifier)
        # build the task on the fly if the identifier is a callable
        elif callable(identifier):
            if hasattr(identifier, "_NodeCls"):
                identifier = identifier._NodeCls
            else:
                identifier = build_node_from_callable(identifier)
        node = self.nodes._new(identifier, name, **kwargs)
        self._version += 1
        return node

    def add_link(self, source: NodeSocket | Node, target: NodeSocket) -> NodeLink:
        """Add a link between two nodes."""
        if isinstance(source, Node):
            source = source.outputs["_outputs"]
        link = self.links._new(source, target)
        self._version += 1
        return link

    def append_node(self, node: Node) -> None:
        """Appends a node to the node graph."""
        self.nodes._append(node)

    def get_node_names(self) -> List[str]:
        """Returns the names of the nodes in the node graph."""
        return self.nodes._get_keys()

    def launch(self) -> None:
        """Launches the node graph."""
        raise NotImplementedError("The 'launch' method is not implemented.")

    def wait(self) -> None:
        """Waits for the node graph to finish.

        Args:
            timeout (int, optional): The maximum time to wait in seconds. Defaults to 50.
        """
        return NotImplementedError("The 'wait' method is not implemented.")

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
        nodes: Dict[str, Any] = self.export_nodes_to_dict(short=short)
        links: List[Dict[str, Any]] = self.links_to_dict()
        data: Dict[str, Any] = {
            "platform_version": f"{self.platform}@{self.platform_version}",
            "uuid": self.uuid,
            "name": self.name,
            "state": self.state,
            "action": self.action,
            "error": "",
            "metadata": metadata,
            "nodes": nodes,
            "links": links,
            "description": self.description,
        }
        return data

    def get_metadata(self) -> Dict[str, Any]:
        """Converts the metadata to a dictionary.

        Returns:
            Dict[str, Any]: The metadata.
        """
        metadata: Dict[str, Any] = {
            "graph_type": self.graph_type,
            "group_properties": self.group_properties,
            "group_inputs": self.group_inputs,
            "group_outputs": self.group_outputs,
        }
        return metadata

    def export_nodes_to_dict(self, short: bool = False) -> Dict[str, Any]:
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
        """Updates the node graph from the database."""
        raise NotImplementedError("The 'update' method is not implemented.")

    @classmethod
    def from_dict(
        cls, ngdata: Dict[str, Any], class_factory: Callable = None
    ) -> "NodeGraph":
        """Rebuilds a node graph from a dictionary.

        Args:
            ngdata (Dict[str, Any]): The data of the node graph.

        Returns:
            NodeGraph: The rebuilt node graph.
        """
        if class_factory is None:
            from node_graph.nodes.factory.base import BaseNodeFactory

            class_factory = BaseNodeFactory
        ng: "NodeGraph" = cls(
            name=ngdata["name"],
            uuid=ngdata.get("uuid"),
            graph_type=ngdata["metadata"].get("graph_type", "NORMAL"),
            state=ngdata.get("state", "CREATED"),
            action=ngdata.get("action", "NONE"),
            description=ngdata.get("description", ""),
            group_properties=ngdata["metadata"].get("group_properties", []),
            group_inputs=ngdata["metadata"].get("group_inputs", []),
            group_outputs=ngdata["metadata"].get("group_outputs", []),
        )
        for name, ndata in ngdata["nodes"].items():
            if ndata.get("metadata", {}).get("is_dynamic", False):
                identifier = class_factory(ndata)
            else:
                identifier = ndata["identifier"]
            node = ng.add_node(
                identifier,
                name=name,
                uuid=ndata.pop("uuid", None),
                _metadata=ndata.get("metadata", None),
                _executor=ndata.get("executor", None),
            )
            node.update_from_dict(ndata)
        for link in ngdata.get("links", []):
            ng.add_link(
                ng.nodes[link["from_node"]].outputs[link["from_socket"]],
                ng.nodes[link["to_node"]].inputs[link["to_socket"]],
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
        ng = self.__class__(name=name, uuid=None)
        ng.nodes = self.nodes._copy(graph=ng)
        for link in self.links:
            ng.add_link(
                ng.nodes[link.from_node.name].outputs[link.from_socket._scoped_name],
                ng.nodes[link.to_node.name].inputs[link.to_socket._scoped_name],
            )
        return ng

    @classmethod
    def load(cls) -> None:
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
            ng.append_node(self.nodes[node_name].copy(graph=ng))
        for link in self.links:
            if (
                add_ref
                and link.from_node.name not in ng.get_node_names()
                and link.to_node.name in ng.get_node_names()
            ):
                ng.append_node(self.nodes[link.from_node.name].copy(graph=ng))
            if (
                link.from_node.name in ng.get_node_names()
                and link.to_node.name in ng.get_node_names()
            ):
                ng.add_link(
                    ng.nodes[link.from_node.name].outputs[link.from_socket._name],
                    ng.nodes[link.to_node.name].inputs[link.to_socket._name],
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
        self.nodes._extend(other.nodes._copy(graph=self))
        for link in other.links:
            self.add_link(
                self.nodes[link.from_node.name].outputs[link.from_socket._name],
                self.nodes[link.to_node.name].inputs[link.to_socket._name],
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

    def delete_nodes(self, node_list: str | List[str]) -> None:
        """Deletes nodes from the node graph.

        Args:
            node_list (List[str]): The names of the nodes to delete.
        """
        if isinstance(node_list, str):
            node_list = [node_list]
        for name in node_list:
            if name not in self.get_node_names():
                raise ValueError(f"Node '{name}' not found in the node graph.")
            link_indices: List[int] = []
            for index, link in enumerate(self.links):
                if link.from_node.name == name or link.to_node.name == name:
                    link_indices.append(index)
            # Delete links in reverse order to avoid index shift
            for index in sorted(link_indices, reverse=True):
                del self.links[index]
            del self.nodes[name]

    def to_widget_value(self) -> dict:
        from node_graph.utils import nodegaph_to_short_json

        ngdata = nodegaph_to_short_json(self.to_dict())
        return ngdata

    def __repr__(self) -> str:
        return f'NodeGraph(name="{self.name}", uuid="{self.uuid}")'

    def _repr_mimebundle_(self, *args, **kwargs):
        # if ipywdigets > 8.0.0, use _repr_mimebundle_ instead of _ipython_display_
        self._widget.value = self.to_widget_value()
        if hasattr(self._widget, "_repr_mimebundle_"):
            return self._widget._repr_mimebundle_(*args, **kwargs)
        else:
            return self._widget._ipython_display_(*args, **kwargs)

    def to_html(self, output: str = None, **kwargs):
        """Write a standalone html file to visualize the graph."""
        self._widget.value = self.to_widget_value()
        return self._widget.to_html(output=output, **kwargs)
