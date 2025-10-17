"""
Node
====

This tutorial introduces the general features of a ``Node`` in the ``node_graph`` framework.

"""
# %%
# Define and register a custom node with a decorator
# --------------------------------------------------
#
# You can register a function as a ``Node`` with a decorator.

from node_graph import node, NodeGraph


@node(
    identifier="MyAdd",
)
def myadd(x, y):
    return x + y


# use the node in a nodegraph
ng2 = NodeGraph(name="test_decorator")
add1 = ng2.add_node(myadd, "add1", x=1, y=2)
add2 = ng2.add_node(myadd, "add2", x=3, y=add1.outputs.result)
ng2.to_html()

# %%
# Define a custom node class
# --------------------------
# You can also define a new node by extending the ``Node`` class.
# This is useful when you want to create a node with dynamic inputs/outputs based on properties.
from node_graph import Node, namespace
from node_graph.node_spec import NodeSpec
from node_graph.executor import RuntimeExecutor


class MyNode(Node):

    _default_spec = NodeSpec(
        identifier="my_package.nodes.my_node",
        catalog="Test",
        inputs=namespace(),
        outputs=namespace(
            result=object,
        ),
        executor=RuntimeExecutor.from_callable(pow),
        base_class_path="my_package.nodes.MyNode",
    )

    def create_properties(self):
        self.add_property("node_graph.int", "t", default=1)
        self.add_property(
            "node_graph.enum",
            "function",
            default="pow",
            options=[
                ["pow", "pow", "pow function"],
                ["sqrt", "sqrt", "sqrt function"],
            ],
            update=self.update_spec,
        )

    def update_spec(self):
        """Callback to update the node spec when properties change."""
        import importlib
        from dataclasses import replace

        if self.properties["function"].value in ["pow"]:
            input_spec = namespace(
                x=float,
                y=float,
            )
        elif self.properties["function"].value in ["sqrt"]:
            input_spec = namespace(
                x=float,
            )
        func = getattr(
            importlib.import_module("math"),
            self.properties["function"].content,
        )
        executor = RuntimeExecutor.from_callable(func)
        self.spec = replace(self.spec, inputs=input_spec, executor=executor)
        self._materialize_from_spec()


# %%
# Entry point
# -----------
#
# One can register the custom node so that it can be used by its identifier in a node graph.
#
# .. code-block:: bash
#
#     [project.entry-points."node_graph.node"]
#     "my_package.my_node" = "my_package.nodes:MyNode"
#
# Then you can create the node by its identifier:
#
# .. code-block:: python
#
#    ng = NodeGraph(name="test_node_usage")
#    float1 = ng.add_node("my_package.my_node", name="float1", value=5)
