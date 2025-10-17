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


@node.graph()
def AddMultiply(x, y, z):
    the_sum = add(x=x, y=y).result
    return multiply(x=the_sum, y=z).result


ng = AddMultiply.build(x=1, y=2, z=3)
ng.to_html()


# %%
# Engines and provenance
# Run graphs directly in Python:
from node_graph_engine.parsl import ParslEngine

graph = AddMultiply.build(x=1, y=2, z=3)

engine = ParslEngine()
results = engine.run(graph)
print("results:", results)

# %%
# Provenance for visualization
# ============================
# In interactive notebooks you can display the provenance graph inline

engine.recorder


# %%
# Node graph programming
# ===========================
# You can also create a node graph programmatically. Three steps:
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
# What's Next
# ==================
#
# +--------------------------------------+----------------------------------------------------+
# | Topic                                | Description                                        |
# +--------------------------------------+----------------------------------------------------+
# | `Concepts <../concept/index.rst>`__  | A brief introduction of NodeGraph main concepts.   |
# +--------------------------------------+----------------------------------------------------+
