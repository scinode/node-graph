from node_graph import Node
from node_graph.nodes.factory.base import BaseNodeFactory


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
    node_class = Node
    factory_class = BaseNodeFactory

    @property
    def outputs(self):
        return self.inputs

    @outputs.setter
    def outputs(self, _value):
        """Outputs are the same as inputs for ctx node."""
        pass

    def get_metadata(self):

        metadata = super().get_metadata()
        metadata["node_class"] = {
            "module_path": self.node_class.__module__,
            "callable_name": self.node_class.__name__,
        }
        metadata["factory_class"] = {
            "module_path": self.factory_class.__module__,
            "callable_name": self.factory_class.__name__,
        }
        return metadata


class GraphInputs(GraphLevelNode):
    identifier = "node_graph.graph_inputs"
    name = "Graph_Inputs"


class GraphOutputs(GraphLevelNode):
    identifier = "node_graph.graph_outputs"
    name = "Graph_Outputs"


class GraphContext(GraphLevelNode):
    identifier = "node_graph.graph_ctx"
    name = "Graph_Ctx"
