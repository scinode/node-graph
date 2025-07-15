from node_graph.collection import EntryPointPool

# global instance
NodePool = EntryPointPool(entry_point_group="node_graph.node")
NodePool["any"] = NodePool.node_graph.node
NodePool["graph_inputs"] = NodePool.node_graph.graph_inputs
NodePool["graph_outputs"] = NodePool.node_graph.graph_outputs
NodePool["graph_ctx"] = NodePool.node_graph.graph_ctx
