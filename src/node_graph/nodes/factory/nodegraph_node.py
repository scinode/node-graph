from typing import TYPE_CHECKING
from .base import BaseNodeFactory
from node_graph.config import builtin_inputs, builtin_outputs
from node_graph import Node

if TYPE_CHECKING:
    from node_graph import NodeGraph


class NodeGraphNode(Node):
    """Node created from NodeGraph."""

    identifier = "nodegraph.nodegraph_node"
    name = "NodeGraphNode"
    node_type = "Normal"
    catalog = "Builtins"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._nodegraph = None

    @property
    def nodegraph(self):
        from node_graph import NodeGraph
        from copy import deepcopy

        if not self._nodegraph:
            graph_data = deepcopy(self.get_executor()["graph_data"])
            self._nodegraph = NodeGraph.from_dict(graph_data)
        return self._nodegraph

    @property
    def nodes(self):
        return self.nodegraph.nodes

    @property
    def links(self):
        return self.nodegraph.links


class NodeGraphNodeFactory(BaseNodeFactory):
    """A factory to create Node from NodeGraph."""

    @classmethod
    def create_node(
        cls,
        nodegraph: "NodeGraph",
    ):
        tdata = {"metadata": {"node_type": "nodegraph"}}
        inputs = {"name": "inputs", "identifier": "node_graph.namespace", "sockets": {}}
        outputs = {
            "name": "outputs",
            "identifier": "node_graph.namespace",
            "sockets": {},
        }

        for node in nodegraph.nodes:
            # inputs
            data = node.inputs._to_dict()
            data["name"] = node.name
            inputs["sockets"][node.name] = data
            # outputs
            data = node.outputs._to_dict()
            data["name"] = node.name
            outputs["sockets"][node.name] = data
        # add built-in sockets
        for input in builtin_inputs:
            inputs["sockets"][input["name"]] = input.copy()
        for output in builtin_outputs:
            outputs["sockets"][output["name"]] = output.copy()
        tdata["inputs"] = inputs
        tdata["outputs"] = outputs
        tdata["identifier"] = nodegraph.name
        # get graph_data from the nodegraph
        graph_data = nodegraph.to_dict()
        executor = {
            "module_path": "node_graph.engine.nodegraph",
            "callable_name": "NodeGraphEngine",
            "graph_data": graph_data,
        }
        tdata["metadata"]["node_class"] = NodeGraphNode
        tdata["executor"] = executor

        NodeCls = cls(tdata)
        return NodeCls
