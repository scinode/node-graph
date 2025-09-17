from __future__ import annotations
from node_graph.registry import RegistryHub, registry_hub
from node_graph.collection import NodeCollection, LinkCollection
from uuid import uuid1
from node_graph.node_spec import NodeSpec
from node_graph.socket_spec import SocketSpec, BaseSocketSpecAPI
from typing import Dict, Any, List, Optional, Union, Callable
import yaml
from node_graph.node import Node
from node_graph.socket import NodeSocket
from node_graph.socket_spec import add_spec_field
from node_graph.link import NodeLink
from node_graph.utils import yaml_to_dict
from node_graph_widget import NodeGraphWidget
from .config import BuiltinPolicy, BUILTIN_NODES


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

    registry: Optional[RegistryHub] = registry_hub
    platform: str = "node_graph"
    _socket_spec = BaseSocketSpecAPI
    Builtins: BuiltinPolicy = BuiltinPolicy()

    def __init__(
        self,
        name: str = "NodeGraph",
        inputs: Optional[SocketSpec | List[str]] = None,
        outputs: Optional[SocketSpec | List[str]] = None,
        uuid: Optional[str] = None,
        graph_type: str = "NORMAL",
        graph: Optional[NodeGraph] = None,
        parent: Optional[Node] = None,
        state: str = "CREATED",
        action: str = "NONE",
        description: str = "",
        interactive_widget: bool = False,
        init_graph_level_nodes: bool = True,
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
        self.graph = graph
        self.parent = parent
        self.NodePool = self.registry.node_pool
        self.SocketPool = self.registry.socket_pool
        self.PropertyPool = self.registry.property_pool
        self.type_mapping = dict(self.registry.type_mapping)
        self.type_promotions = set(self.registry.type_promotion)
        self.nodes = NodeCollection(graph=self, pool=self.NodePool)
        self.links = LinkCollection(self)
        self.state = state
        self.action = action
        self.description = description
        self._widget = None
        self.interactive_widget = interactive_widget
        self._version = 0  # keep track the changes
        self._inputs = inputs
        self._outputs = outputs
        if init_graph_level_nodes:
            self._init_graph_level_nodes(inputs, outputs)

    def _init_graph_level_nodes(self, inputs, outputs):
        from dataclasses import replace

        inputs = self._socket_spec.validate_socket_data(inputs)
        outputs = self._socket_spec.validate_socket_data(outputs)

        base_class = self.NodePool["graph_level"].load()

        # if inputs is None, we assume it's a dynamic inputs
        inputs = self._socket_spec.dynamic(Any) if inputs is None else inputs
        meta = replace(inputs.meta, sub_socket_default_link_limit=1000000)
        inputs = replace(inputs, meta=meta)
        self._inputs = inputs
        self.graph_inputs_spec = NodeSpec(
            identifier="graph_inputs",
            inputs=inputs,
            base_class=base_class,
        )
        self.nodes._new(self.graph_inputs_spec, name="graph_inputs")
        # if outputs is None, we assume it's a dynamic outputs
        outputs = self._socket_spec.dynamic(Any) if outputs is None else outputs
        self._outputs = outputs
        self.graph_outputs_spec = NodeSpec(
            identifier="graph_outputs",
            inputs=outputs,
            base_class=base_class,
        )
        graph_outputs = self.nodes._new(self.graph_outputs_spec, name="graph_outputs")
        graph_outputs.inputs._name = "outputs"
        # graph context
        ctx = self._socket_spec.dynamic(Any)
        meta = replace(ctx.meta, sub_socket_default_link_limit=1000000)
        ctx = replace(ctx, meta=meta)
        self.graph_ctx_spec = NodeSpec(
            identifier="graph_ctx",
            inputs=ctx,
            base_class=base_class,
        )
        graph_ctx = self.nodes._new(self.graph_ctx_spec, name="graph_ctx")
        graph_ctx.inputs._name = "ctx"

    @property
    def graph_inputs(self) -> Node:
        """Group inputs node."""
        return self.nodes["graph_inputs"]

    @property
    def graph_outputs(self) -> Node:
        """Group outputs node."""
        return self.nodes["graph_outputs"]

    @property
    def graph_ctx(self) -> Node:
        """Context variable node."""
        return self.nodes["graph_ctx"]

    @property
    def inputs(self) -> Node:
        """Group inputs node."""
        return self.graph_inputs.inputs

    @inputs.setter
    def inputs(self, value: Dict[str, Any]) -> None:
        """Set group inputs node."""
        self.graph_inputs.inputs._set_socket_value(value)

    @property
    def outputs(self) -> Node:
        """Group outputs node."""
        return self.graph_outputs.inputs

    @outputs.setter
    def outputs(self, value: Dict[str, Any]) -> None:
        """Set group outputs node."""
        self.graph_outputs.inputs._set_socket_value(value)

    @property
    def ctx(self) -> Node:
        """Context node."""
        return self.graph_ctx.inputs

    @ctx.setter
    def ctx(self, value: Dict[str, Any]) -> None:
        """Set context node."""
        self.graph_ctx.inputs._clear()
        self.graph_ctx.inputs._set_socket_value(value, link_limit=100000)

    def expose_inputs(self, names: Optional[List[str]] = None) -> None:
        """Generate group inputs from nodes."""
        self.inputs._clear()
        all_names = set(self.nodes._get_keys())
        names = set(names or all_names)
        missing = names - all_names
        if missing:
            raise ValueError(f"The following named nodes do not exist: {missing}")
        for name in names - set(BUILTIN_NODES):
            node = self.nodes[name]
            # skip linked sockets
            socket = node.inputs._copy(
                node=self.graph_inputs,
                parent=self.inputs,
                skip_linked=True,
                skip_builtin=True,
            )
            socket._name = node.name
            self.inputs._append(socket)
            # update the _inputs spec
            if hasattr(node, "_spec") and node._spec.inputs is not None:
                self._inputs = add_spec_field(
                    self._inputs, node.name, node._spec.inputs
                )
            else:
                raise ValueError(
                    f"Node {node.name} does not have inputs spec, cannot expose inputs."
                )
            keys = node.inputs._get_all_keys()
            exist_keys = socket._get_all_keys()
            for key in keys:
                new_key = f"{node.name}.{key}"
                if new_key not in exist_keys:
                    continue
                # add link from group inputs to node inputs
                self.add_link(self.inputs[new_key], node.inputs[key])

    def expose_outputs(self, names: Optional[List[str]] = None) -> None:
        """Generate group outputs from nodes."""
        self.outputs._clear()
        all_names = set(self.nodes._get_keys())
        names = set(names or all_names)
        missing = names - all_names
        if missing:
            raise ValueError(f"The following named nodes do not exist: {missing}")
        for name in names - set(BUILTIN_NODES):
            node = self.nodes[name]
            socket = node.outputs._copy(
                node=self.graph_outputs,
                parent=self.outputs,
                skip_builtin=True,
            )
            socket._name = node.name
            self.outputs._append(socket)
            # update the _outputs spec
            if hasattr(node, "_spec") and node._spec.outputs is not None:
                self._outputs = add_spec_field(
                    self._outputs, node.name, node._spec.outputs
                )
            else:
                raise ValueError(
                    f"Node {node.name} does not have outputs spec, cannot expose outputs."
                )
            keys = node.outputs._get_all_keys()
            exist_keys = socket._get_all_keys()
            for key in keys:
                new_key = f"{node.name}.{key}"
                if new_key not in exist_keys:
                    continue
                # add link from node outputs to group outputs
                self.add_link(node.outputs[key], self.outputs[new_key])

    def set_inputs(self, inputs: Dict[str, Any]):
        for name, input in inputs.items():
            if "graph_inputs" in self.nodes and name in self.inputs:
                setattr(self.inputs, name, input)
            elif name in self.nodes:
                self.nodes[name].set_inputs(input)
            else:
                raise KeyError(
                    f"{name} does not exist. Accepted keys are: {list(self.get_node_names()) + ['graph_inputs']}."
                )

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
        self,
        identifier: Union[str, Callable],
        name: str = None,
        include_builtins: bool = False,
        **kwargs,
    ) -> Node:
        """Adds a node to the node graph."""

        from node_graph.decorator import build_node_from_callable
        from node_graph.node_spec import NodeHandle
        from node_graph.nodes.subgraph_node import _build_subgraph_task_nodespec

        if name in BUILTIN_NODES and not include_builtins:
            raise ValueError(f"Name {name} can not be used, it is reserved.")

        if isinstance(identifier, NodeGraph):
            identifier = _build_subgraph_task_nodespec(graph=identifier, name=name)
        # build the task on the fly if the identifier is a callable
        elif callable(identifier) and not isinstance(
            identifier, (NodeSpec, NodeHandle)
        ):
            identifier = build_node_from_callable(identifier)
        node = self.nodes._new(identifier, name, **kwargs)
        self._version += 1
        return node

    def add_link(self, source: NodeSocket | Node, target: NodeSocket) -> NodeLink:
        """Add a link between two nodes."""
        from node_graph.socket import NodeSocketNamespace

        if isinstance(source, Node):
            source = source.outputs["graph_outputs"]
        elif source._parent is None and isinstance(source, NodeSocketNamespace):
            # if the source is the top-level outputs,
            # we use the built-in "_outputs" socket to represent it
            if "_outputs" in source:
                source = source["_outputs"]
            else:
                raise ValueError(
                    f"You try to link a top-level output socket {source._name} without a parent."
                )
        #
        key = f"{source._node.name}.{source._scoped_name} -> {target._node.name}.{target._scoped_name}"
        if key in self.links:
            return self.links[key]
        link = self.links._new(source, target)
        self._version += 1
        return link

    def add_input(self, identifier: str, name: str, **kwargs) -> NodeSocket:
        """Add an input socket to this node."""

        input = self.inputs._new(identifier, name, **kwargs)
        return input

    def add_output(self, identifier: str, name: str, **kwargs) -> NodeSocket:
        output = self.outputs._new(identifier, name, **kwargs)
        return output

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
        self, include_sockets: bool = False, should_serialize: bool = False
    ) -> Dict[str, Any]:
        """Converts the node graph to a dictionary.

        Args:
            short (bool, optional): Indicates whether to include short node representations. Defaults to False.

        Returns:
            Dict[str, Any]: The node graph data.
        """
        metadata = self.get_metadata()
        nodes = self.export_nodes_to_dict(
            include_sockets=include_sockets, should_serialize=should_serialize
        )

        links = self.links_to_dict()
        data = {
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
        """Export graph metadata including *live* graph-level IO specs."""
        meta: Dict[str, Any] = {
            "graph_type": self.graph_type,
        }
        if self._inputs is not None:
            meta["inputs_spec"] = self._inputs.to_dict()
        if self._outputs is not None:
            meta["outputs_spec"] = self._outputs.to_dict()
        # also save the parent class information
        meta["graph_class"] = {
            "callable_name": self.__class__.__name__,
            "module_path": self.__class__.__module__,
        }
        return meta

    def export_nodes_to_dict(
        self, include_sockets: bool = False, should_serialize: bool = False
    ) -> Dict[str, Any]:
        """Converts the nodes to a dictionary.

        Args:
            short (bool, optional): Indicates whether to include short node representations. Defaults to False.

        Returns:
            Dict[str, Any]: The nodes data.
        """
        # generate spec for graph-level nodes
        nodes = {}
        for node in self.nodes:
            nodes[node.name] = node.to_dict(
                include_sockets=include_sockets, should_serialize=should_serialize
            )
        return nodes

    def links_to_dict(self) -> List[Dict[str, Any]]:
        """Converts the links to a list of dictionaries.

        Returns:
            List[Dict[str, Any]]: The links data.
        """
        links = []
        for link in self.links:
            links.append(link.to_dict())
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

    def links_from_dict(self, links: list) -> None:
        """Adds links to the node graph from a dictionary.

        Args:
            links (List[Dict[str, Any]]): The links data.
        """
        for link in links:
            self.nodes[link["to_node"]].set_inputs(
                {
                    link["to_socket"]: self.nodes[link["from_node"]].outputs[
                        link["from_socket"]
                    ]
                }
            )

    @classmethod
    def from_dict(cls, ngdata: Dict[str, Any]) -> NodeGraph:
        """Rebuilds a node graph from a dictionary.

        Args:
            ngdata (Dict[str, Any]): The data of the node graph.

        Returns:
            NodeGraph: The rebuilt node graph.
        """

        md = ngdata.get("metadata", {}) or {}

        ng = cls(
            name=ngdata["name"],
            uuid=ngdata.get("uuid"),
            graph_type=ngdata["metadata"].get("graph_type", "NORMAL"),
            state=ngdata.get("state", "CREATED"),
            action=ngdata.get("action", "NONE"),
            description=ngdata.get("description", ""),
            init_graph_level_nodes=False,
        )
        # built-in graph level nodes
        inputs_spec = (
            SocketSpec.from_dict(md["inputs_spec"], type_mapping=ng.type_mapping)
            if "inputs_spec" in md
            else None
        )
        outputs_spec = (
            SocketSpec.from_dict(md["outputs_spec"], type_mapping=ng.type_mapping)
            if "outputs_spec" in md
            else None
        )
        ng._init_graph_level_nodes(inputs_spec, outputs_spec)

        for ndata in ngdata["nodes"].values():
            ng.add_node_from_dict(ndata)

        ng.links_from_dict(ngdata.get("links", []))
        return ng

    def add_node_from_dict(self, ndata: Dict[str, Any]) -> Node:
        """Adds a node to the node graph from a dictionary.

        Args:
            ndata (Dict[str, Any]): The data of the node.

        Returns:
            Node: The added node.
        """
        import importlib

        md = ndata.get("metadata", {}) or {}
        name = ndata["name"]
        if name in BUILTIN_NODES:
            self.nodes[name].update_from_dict(ndata)
            return self.nodes[name]
        else:
            if md.get("is_dynamic", False):
                node_class = ndata.get("metadata", {}).get("node_class", None)
                node_class = getattr(
                    importlib.import_module(node_class["module_path"]),
                    node_class["callable_name"],
                )
                node = node_class.from_dict(ndata, graph=self)
                self.nodes._append(node)
            else:
                identifier = md["identifier"]
                node = self.add_node(
                    identifier,
                    name=name,
                    uuid=ndata.pop("uuid", None),
                    _metadata=ndata.get("metadata", None),
                    _executor=ndata.get("executor", None),
                    include_builtins=ndata["name"] in BUILTIN_NODES,
                )
                node.update_from_dict(ndata)
        return node

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
        nodes = other.nodes._copy(graph=self)
        for node in nodes:
            # skip built-in nodes
            if node.name not in BUILTIN_NODES:
                self.nodes._append(node)
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

        ngdata = nodegaph_to_short_json(self.to_dict(include_sockets=True))
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

    def __enter__(self):
        from node_graph.manager import active_graph as _active_graph

        self.___ctx = _active_graph(self)
        self.___ctx.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb):
        return self.___ctx.__exit__(exc_type, exc, tb)
