from __future__ import annotations
from node_graph.node import Node
from node_graph.node_spec import NodeSpec


class SubGraphNode(Node):
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

    meta = {
        "node_type": "WorkGraph",
    }

    return NodeSpec(
        identifier=graph.name,
        inputs=graph.spec.inputs,
        outputs=graph.spec.outputs,
        executor=RuntimeExecutor.from_graph(graph),
        base_class=SubGraphNode,
        metadata=meta,
    )
