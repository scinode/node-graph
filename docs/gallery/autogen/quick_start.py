"""
===========
Quick Start
===========

"""

# %%
# Installation
# ==================
# Let's first install ``node-graph`` via pip:
#
# .. code:: console
#
#    $ pip install node-graph
#
# First workflow
# ==================
# Suppose we want to calculate ``(x + y) * z`` in two steps.
#
# - step 1: add `x` and `y`
# - step 2: then multiply the result with `z`.
#

# %%
# Create task
# ------------------
# Task is the basic building block of a workflow. One can create a task from a Python function using the `decorator`:

# %%
from node_graph.decorator import task


@task()
def add(x, y):
    return x + y


@task()
def multiply(x, y):
    return x * y


@task.graph()
def AddMultiply(x, y, z):
    the_sum = add(x=x, y=y).result
    return multiply(x=the_sum, y=z).result


ng = AddMultiply.build(x=1, y=2, z=3)
ng.to_html()


# %%
# Engines and provenance
# Run graphs directly in Python:
from node_graph.engine.local import LocalEngine

graph = AddMultiply.build(x=1, y=2, z=3)

engine = LocalEngine()
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
# You can also create a graph programmatically. Three steps:
#
# - create a empty `Graph`
# - add nodes: `add` and `multiply`.
# - link the output of the `add` task to one of the `x` input of the `multiply` task.

# %%
from node_graph import Graph

ng = Graph("first_workflow")
ng.add_task(add, name="add", x=2, y=3)
ng.add_task(multiply, name="multiply", y=4)
ng.add_link(ng.tasks.add.outputs.result, ng.tasks.multiply.inputs.x)
ng.to_html()

# %%
# What's Next
# ==================
#
# +--------------------------------------+----------------------------------------------------+
# | Topic                                | Description                                        |
# +--------------------------------------+----------------------------------------------------+
# | `Concepts <../concept/index.rst>`__  | A brief introduction of main concepts.   |
# +--------------------------------------+----------------------------------------------------+
