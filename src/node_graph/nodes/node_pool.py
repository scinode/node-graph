from node_graph.collection import EntryPointPool

# global instance
NodePool = EntryPointPool(entry_point_group="node_graph.node")
NodePool["any"] = NodePool.node_graph.node
