from __future__ import annotations

from node_graph.collection import NodeCollection, LinkCollection
from uuid import uuid1
from node_graph.sockets import SocketPool
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
    SocketPool = SocketPool
    platform: str = "node_graph"

    def __init__(
        self,
        name: str = "NodeGraph",
        uuid: Optional[str] = None,
        graph_type: str = "NORMAL",
        state: str = "CREATED",
        action: str = "NONE",
        description: str = "",
        interactive_widget: bool = False,
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
        self.init_meta_nodes()
        self.state = state
        self.action = action
        self.description = description
        self._widget = None
        self.interactive_widget = interactive_widget
        self._version = 0  # keep track the changes

    def init_meta_nodes(self) -> None:
        self.meta_nodes = NodeCollection(self, pool=self.NodePool)
        # add group_inputs and group_outputs nodes
        group_inputs = self.meta_nodes._new("any", name="group_inputs")
        group_inputs.outputs._socket_is_dynamic = True
        group_outputs = self.meta_nodes._new("any", name="group_outputs")
        group_outputs.inputs._socket_is_dynamic = True
        ctx = self.meta_nodes._new("any", name="ctx")
        ctx.inputs._socket_is_dynamic = True
        ctx.inputs._default_link_limit = 1e6

    @property
    def group_inputs(self) -> Node:
        """Group inputs node."""
        return self.meta_nodes["group_inputs"].outputs

    @group_inputs.setter
    def group_inputs(self, value: Dict[str, Any]) -> None:
        """Set group inputs node."""
        self.meta_nodes["group_inputs"].outputs._clear()
        self.meta_nodes["group_inputs"].outputs._set_socket_value(value)

    @property
    def group_outputs(self) -> Node:
        """Group outputs node."""
        return self.meta_nodes["group_outputs"].inputs

    @group_outputs.setter
    def group_outputs(self, value: Dict[str, Any]) -> None:
        """Set group outputs node."""
        self.meta_nodes["group_outputs"].inputs._clear()
        self.meta_nodes["group_outputs"].inputs._set_socket_value(value)

    @property
    def ctx(self) -> Node:
        """Context node."""
        return self.meta_nodes["ctx"].inputs

    @ctx.setter
    def ctx(self, value: Dict[str, Any]) -> None:
        """Set context node."""
        self.meta_nodes["ctx"].inputs._clear()
        self.meta_nodes["ctx"].inputs._set_socket_value(value, link_limit=100000)

    def generate_group_inputs(self) -> None:
        """Generate group inputs from nodes."""
        self.group_inputs._clear()
        for node in self.nodes:
            # skip linked sockets
            socket = node.inputs._copy(
                node=self.meta_nodes["group_inputs"],
                parent=self.group_inputs,
                skip_linked=True,
                skip_builtin=True,
            )
            socket._name = node.name
            self.group_inputs._append(socket)
            keys = node.inputs._get_all_keys()
            exist_keys = socket._get_all_keys()
            for key in keys:
                new_key = f"{node.name}.{key}"
                if new_key not in exist_keys:
                    continue
                # add link from group inputs to node inputs
                self.add_link(self.group_inputs[new_key], node.inputs[key])

    def generate_group_outputs(self) -> None:
        """Generate group outputs from nodes."""
        self.group_outputs._clear()
        for node in self.nodes:
            socket = node.outputs._copy(
                node=self.meta_nodes["group_outputs"],
                parent=self.group_outputs,
                skip_builtin=True,
            )
            socket._name = node.name
            self.group_outputs._append(socket)
            keys = node.outputs._get_all_keys()
            exist_keys = socket._get_all_keys()
            for key in keys:
                new_key = f"{node.name}.{key}"
                if new_key not in exist_keys:
                    continue
                # add link from node outputs to group outputs
                self.add_link(node.outputs[key], self.group_outputs[new_key])

    @property
    def meta_sockets(self) -> Node:
        """Meta sockets node."""
        return {
            "group_inputs": self.group_inputs,
            "group_outputs": self.group_outputs,
            "ctx": self.ctx,
        }

    @property
    def platform_version(self) -> str:
        """Retrieve the platform version dynamically from the package where Graph is implemented."""
        import importlib.metadata

        try:
            package_name = self.platform.replace("-", "_")
            return importlib.metadata.version(package_name)
        except importlib.metadata.PackageNotFoundError:
            return "unknown"

    @property
    def widget(self) -> NodeGraphWidget:
        if self._widget is None:
            self._widget = NodeGraphWidget(parent=self)
        return self._widget

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

    def to_dict(
        self, short: bool = False, should_serialize: bool = False
    ) -> Dict[str, Any]:
        """Converts the node graph to a dictionary.

        Args:
            short (bool, optional): Indicates whether to include short node representations. Defaults to False.

        Returns:
            Dict[str, Any]: The node graph data.
        """
        metadata = self.get_metadata()
        nodes = self.export_nodes_to_dict(
            short=short, should_serialize=should_serialize
        )

        links, meta_links = self.links_to_dict()
        data = {
            "platform_version": f"{self.platform}@{self.platform_version}",
            "uuid": self.uuid,
            "name": self.name,
            "state": self.state,
            "action": self.action,
            "error": "",
            "metadata": metadata,
            "nodes": nodes,
            "meta_sockets": self.meta_sockets_to_dict(),
            "links": links,
            "meta_links": meta_links,
            "description": self.description,
        }
        return data

    def meta_sockets_to_dict(self) -> Dict[str, Any]:
        meta_sockets = {
            "ctx": self.ctx._value,
            "group_inputs": self.group_inputs._value,
            "group_outputs": self.group_outputs._value,
        }
        return meta_sockets

    def meta_sockets_from_dict(self, meta_sockets: Dict[str, Any]) -> None:
        self.ctx = meta_sockets.get("ctx", {})
        self.group_inputs = meta_sockets.get("group_inputs", {})
        self.group_outputs = meta_sockets.get("group_outputs", {})

    def get_metadata(self) -> Dict[str, Any]:
        """Converts the metadata to a dictionary.

        Returns:
            Dict[str, Any]: The metadata.
        """
        metadata: Dict[str, Any] = {
            "graph_type": self.graph_type,
            # "group_inputs": self.group_inputs,
            # "group_outputs": self.group_outputs,
        }
        return metadata

    def export_nodes_to_dict(
        self, short: bool = False, should_serialize: bool = False
    ) -> Dict[str, Any]:
        """Converts the nodes to a dictionary.

        Args:
            short (bool, optional): Indicates whether to include short node representations. Defaults to False.

        Returns:
            Dict[str, Any]: The nodes data.
        """
        nodes = {}
        for node in self.nodes:
            nodes[node.name] = node.to_dict(
                short=short, should_serialize=should_serialize
            )
        return nodes

    def links_to_dict(self) -> List[Dict[str, Any]]:
        """Converts the links to a list of dictionaries.

        Returns:
            List[Dict[str, Any]]: The links data.
        """
        links = []
        meta_links = []
        for link in self.links:
            if (
                link.from_node.name in self.meta_nodes
                or link.to_node.name in self.meta_nodes
            ):
                meta_links.append(link.to_dict())
            else:
                links.append(link.to_dict())
        return links, meta_links

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

    def links_from_dict(self, links: list, meta_links: list) -> None:
        """Adds links to the node graph from a dictionary.

        Args:
            links (List[Dict[str, Any]]): The links data.
        """
        for link in links:
            self.add_link(
                self.nodes[link["from_node"]].outputs[link["from_socket"]],
                self.nodes[link["to_node"]].inputs[link["to_socket"]],
            )
        # add meta links
        for link in meta_links:
            if link["from_node"] in self.meta_sockets:
                meta_socket = self.meta_sockets[link["from_node"]]
                if link["from_socket"] not in meta_socket:
                    meta_socket._set_socket_value(
                        {link["from_socket"]: None}, link_limit=100000
                    )
                if link["to_node"] in self.meta_sockets:
                    if link["to_socket"] not in self.meta_sockets[link["to_node"]]:
                        self.meta_sockets[link["to_node"]]._set_socket_value(
                            {link["to_socket"]: None}, link_limit=100000
                        )
                    to_socket = self.meta_sockets[link["to_node"]][link["to_socket"]]
                else:
                    to_socket = self.nodes[link["to_node"]].inputs[link["to_socket"]]
                self.add_link(meta_socket[link["from_socket"]], to_socket)
            elif link["to_node"] in self.meta_sockets:
                meta_socket = self.meta_sockets[link["to_node"]]
                if link["from_node"] in self.meta_sockets:
                    from_socket = self.meta_sockets[link["from_node"]][
                        link["from_socket"]
                    ]
                else:
                    from_socket = self.nodes[link["from_node"]].outputs[
                        link["from_socket"]
                    ]
                meta_socket._set_socket_value(
                    {link["to_socket"]: from_socket},
                    link_limit=100000,
                )

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
            # group_inputs=ngdata["metadata"].get("group_inputs", []),
            # group_outputs=ngdata["metadata"].get("group_outputs", []),
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
        ng.meta_sockets_from_dict(ngdata.get("meta_sockets", {}))
        ng.links_from_dict(ngdata.get("links", []), ngdata.get("meta_links", []))
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
        self.widget.value = self.to_widget_value()
        if hasattr(self.widget, "_repr_mimebundle_"):
            return self.widget._repr_mimebundle_(*args, **kwargs)
        else:
            return self.widget._ipython_display_(*args, **kwargs)

    def to_html(self, output: str = None, **kwargs):
        """Write a standalone html file to visualize the graph."""
        self.widget.value = self.to_widget_value()
        return self.widget.to_html(output=output, **kwargs)
