"""
Node
====

This tutorial introduces the general features of a ``Node`` in the
``node_graph`` framework.

A node can have the following features:

- metadata, for example name, state, type
- properties (optional)
- input and output sockets (optional)
- executor, a function or class that processes node data
"""

# %%
# Metadata
# --------
#
# Each node has metadata such as:
#
# - ``identifier``: identifier of this node class
# - ``name``: name of this node
#
# In the following example we create a simple node graph and add two float nodes.

from node_graph import NodeGraph

# identifier: node_graph.test_float, name: float1
ng = NodeGraph(name="test_node")
node1 = ng.add_node("node_graph.test_float", name="float1")
node2 = ng.add_node("node_graph.test_float", name="float2")
print(f"Created nodes: {node1}, {node2}")

# %%
# Executor
# --------
#
# An executor is a Python class or function for processing node data.
# It uses the node properties, inputs, outputs and context information
# as positional and keyword arguments.
#
#
# Define and register a custom node with a decorator
# --------------------------------------------------
#
# You can register a function as a ``Node`` with a decorator.
# The decorator creates the ``Node`` that uses the function as its executor
# and adds it to the node list.

from node_graph import node


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
#
# You can also define a new node by extending the ``Node`` class.

from node_graph import Node


class TestAdd(Node):
    """TestAdd

    Inputs:
       t (int): delay time in seconds
       x (float)
       y (float)

    Outputs:
       Result (float)
    """

    identifier: str = "TestAdd"
    name = "TestAdd"
    catalog = "Test"

    def create_properties(self):
        self.add_property("node_graph.int", "t", default=1)

    def update_sockets(self):
        self.inputs._clear()
        self.outputs._clear()
        self.add_input("node_graph.float", "x")
        self.add_input("node_graph.float", "y")
        self.add_output("node_graph.float", "Result")

    def get_executor(self):
        executor = {
            "module_path": "node_graph.executors.test.test_add",
        }
        return executor


print("Defined custom node class TestAdd with identifier:", TestAdd.identifier)

# %%
# Use node
# --------
#
# Create a node inside a ``NodeGraph``, set inputs, copy it, and append it.

ng3 = NodeGraph(name="test_node_usage")
float1 = ng3.add_node("node_graph.test_float", name="float1", value=5)


# %%
# .. autoclass:: node_graph.node.Node
#    :members:
#
