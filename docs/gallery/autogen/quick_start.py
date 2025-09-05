"""
===========
Quick Start
===========

"""

# %%
# First workflow
# ==================
# Suppose we want to calculate ``(x + y) * z`` in two steps.
#
# - step 1: add `x` and `y`
# - step 2: then multiply the result with `z`.
#

# %%
# Create node
# ------------------
# Node is the basic building block of a workflow. One can create a node from a Python function using the `decorator`:

# %%
from node_graph.decorator import node


@node()
def add(x, y):
    return x + y


@node()
def multiply(x, y):
    return x * y


# %%
# Create the workflow
# -----------------------
# Three steps:
#
# - create a empty `NodeGraph`
# - add nodes: `add` and `multiply`.
# - link the output of the `add` node to one of the `x` input of the `multiply` node.

# %%
from node_graph import NodeGraph

ng = NodeGraph("first_workflow")
ng.add_node(add, name="add", x=2, y=3)
ng.add_node(multiply, name="multiply", y=4)
ng.add_link(ng.nodes.add.outputs.result, ng.nodes.multiply.inputs.x)
ng.to_html()

# %%
# Node group
# ==============
# A `NodeGraph` is a group of nodes.
# One can treat a `NodeGraph` as a single node, and expose the inputs and outputs of the `NodeGraph`.
# This allow you to write nested workflows.
#

# %%
from node_graph import NodeGraph
from node_graph.decorator import node


@node.graph()
def add_multiply(x, y, z):
    add_out = add(x=x, y=y).result
    return multiply(x=z, y=add_out).result


# %%
# Build the node group
#

ng = add_multiply.build_graph(1, 2, 3)
ng.to_html()


# %%
# Use this node group inside a `NodeGraph`:

# %%
from node_graph import NodeGraph

ng = NodeGraph("test_node_group")
# create a node using the node group
add_multiply1 = ng.add_node(add_multiply, x=2, y=3, z=4)
add_multiply2 = ng.add_node(add_multiply, x=2, y=3)
# link the output of int node to the input of add node
ng.add_link(add_multiply1.outputs.result, add_multiply2.inputs.z)
ng.to_html()

# %%
# What's Next
# ==================
#
# +--------------------------------------+----------------------------------------------------+
# | Topic                                | Description                                        |
# +--------------------------------------+----------------------------------------------------+
# | `Concepts <../concept/index.rst>`__  | A brief introduction of NodeGraph main concepts.   |
# +--------------------------------------+----------------------------------------------------+
