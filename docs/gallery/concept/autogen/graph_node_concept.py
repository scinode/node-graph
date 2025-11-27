"""
Graph task
==========

Conceptually, graph task let you treat a set of tasks as one task.
They are similar to functions in programming since they can be reused and
customized by changing their parameters.

Graph nodes can be nested, and they can also call themselves recursively.

"""

# %%
# Define a graph task with a decorator
# ------------------------------------
#
# You can define a graph task with the ``task.graph`` decorator. In the group
# definition you can also set default values for task properties.

from node_graph.decorator import task


@task()
def add(x, y):
    return x + y


@task()
def multiply(x, y):
    return x * y


@task.graph()
def add_multiply(x, y, z):
    add_out = add(x=x, y=y).result
    return multiply(x=z, y=add_out).result


# %%
# Build the task group
#

ng = add_multiply.build(1, 2, 3)
ng.to_html()


# %%
# Use the graph task like a normal task
# -------------------------------------------
#
# Create a task graph, add the group, set inputs, and run.

from node_graph import Graph

g1 = Graph(name="group_usage")
grp = g1.add_task(add_multiply, name="my_group")
g1.to_html()
