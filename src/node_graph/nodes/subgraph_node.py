from __future__ import annotations
from node_graph.spec_node import SpecNode
from node_graph.node_spec import NodeSpec
from node_graph.socket_spec import SocketSpec


class SubGraphNode(SpecNode):
    """Wrap a NodeGraph instance so it can be used as a Node in a parent graph.

    - Inputs mirror the child graph's *graph_inputs* namespace
    - Outputs mirror the child graph's *graph_outputs* namespace
    - We embed the child graph's serialized dict in metadata for persistence
    """

    identifier = "node_graph.subgraph"
    name = "SubGraphNode"
    node_type = "Normal"
    catalog = "Builtins"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._subgraph = None

    @property
    def subgraph(self):
        from node_graph import NodeGraph
        from copy import deepcopy

        if not self._subgraph:
            graph_data = deepcopy(self.get_executor().graph_data)
            self._subgraph = NodeGraph.from_dict(graph_data)
        return self._subgraph

    @property
    def nodes(self):
        return self.subgraph.nodes

    @property
    def links(self):
        return self.subgraph.links


def _build_subgraph_task_nodespec(
    graph: "NodeGraph",
    name: str | None = None,
) -> NodeSpec:
    from node_graph.executor import RuntimeExecutor

    # mirror IO from the child graph
    if graph._inputs is None:
        in_spec = SocketSpec.from_namespace(graph.graph_inputs.inputs)
    else:
        in_spec = graph._inputs
    if graph._outputs is None:
        out_spec = SocketSpec.from_namespace(graph.graph_outputs.inputs)
    else:
        out_spec = graph._outputs

    meta = {
        "node_type": "WorkGraph",
    }

    return NodeSpec(
        identifier=graph.name,
        inputs=in_spec,
        outputs=out_spec,
        executor=RuntimeExecutor.from_graph(graph),
        base_class=SubGraphNode,
        metadata=meta,
    )
