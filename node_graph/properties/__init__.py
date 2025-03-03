from node_graph.collection import EntryPointPool

# global instance
PropertyPool = EntryPointPool(entry_point_group="node_graph.property")
PropertyPool["any"] = PropertyPool.node_graph.any
