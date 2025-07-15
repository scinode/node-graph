from node_graph import Node


class GraphBuilderNode(Node):
    """Graph builder node"""

    identifier = "nodegraph.graph_builder"
    name = "graph_builder"
    node_type = "graph_builder"
    catalog = "builtins"


class GraphLevelNode(Node):
    """Base class for graph level nodes"""

    catalog = "Builtins"
    is_dynamic: bool = True

    def get_metadata(self):
        from node_graph.nodes.factory.base import BaseNodeFactory

        metadata = super().get_metadata()
        metadata["node_class"] = {
            "module_path": Node.__module__,
            "callable_name": Node.__name__,
        }
        metadata["factory_class"] = {
            "module_path": BaseNodeFactory.__module__,
            "callable_name": BaseNodeFactory.__name__,
        }
        return metadata


class GraphInputs(GraphLevelNode):
    identifier = "node_graph.graph_inputs"
    name = "Graph_Inputs"


class GraphOutputs(GraphLevelNode):
    identifier = "node_graph.graph_outputs"
    name = "Graph_Outputs"


class GraphCtx(GraphLevelNode):
    identifier = "node_graph.graph_ctx"
    name = "Graph_Ctx"

    @property
    def outputs(self):
        return self.inputs

    @outputs.setter
    def outputs(self, _value):
        """Outputs are the same as inputs for ctx node."""
        pass
