from node_graph.registry import EntryPointPool

# global instance
NodePool = EntryPointPool(entry_point_group="node_graph.node")
NodePool["any"] = NodePool.node_graph.node
NodePool["graph_level"] = NodePool.node_graph.graph_level
