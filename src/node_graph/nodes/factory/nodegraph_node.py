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
        inputs = []
        outputs = []
        group_outputs = []
        # add all the inputs/outputs from the nodes in the nodegraph
        builtin_input_names = [input["name"] for input in builtin_inputs]
        builtin_output_names = [output["name"] for output in builtin_outputs]

        for node in nodegraph.nodes:
            # inputs
            inputs.append(
                {
                    "identifier": "node_graph.namespace",
                    "name": f"{node.name}",
                }
            )
            for socket in node.inputs:
                if socket._name in builtin_input_names:
                    continue
                inputs.append(
                    {
                        "identifier": socket._identifier,
                        "name": f"{node.name}.{socket._name}",
                    }
                )
            # outputs
            outputs.append(
                {
                    "identifier": "node_graph.namespace",
                    "name": f"{node.name}",
                }
            )
            for socket in node.outputs:
                if socket._name in builtin_output_names:
                    continue
                outputs.append(
                    {
                        "identifier": socket._identifier,
                        "name": f"{node.name}.{socket._name}",
                    }
                )
                group_outputs.append(
                    {
                        "name": f"{node.name}.{socket._name}",
                        "from": f"{node.name}.{socket._name}",
                    }
                )
        # add built-in sockets
        for output in builtin_outputs:
            outputs.append(output.copy())
        for input in builtin_inputs:
            inputs.append(input.copy())
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
        tdata["metadata"]["group_outputs"] = group_outputs
        tdata["metadata"]["node_class"] = NodeGraphNode
        tdata["executor"] = executor

        NodeCls = cls(tdata)
        return NodeCls
