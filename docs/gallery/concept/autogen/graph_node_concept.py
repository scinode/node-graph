"""
Graph node
==========

Conceptually, graph node let you treat a set of nodes as one node.
They are similar to functions in programming since they can be reused and
customized by changing their parameters.

Graph nodes can be nested, and they can also call themselves recursively.

"""

# %%
# Define a graph node with a decorator
# ------------------------------------
#
# You can define a graph node with the ``node.graph`` decorator. In the group
# definition you can also set default values for node properties.

from node_graph.decorator import node


@node()
def add(x, y):
    return x + y


@node()
def multiply(x, y):
    return x * y


@node.graph()
def add_multiply(x, y, z):
    add_out = add(x=x, y=y).result
    return multiply(x=z, y=add_out).result


# %%
# Build the node group
#

ng = add_multiply.build(1, 2, 3)
ng.to_html()


# %%
# Use the graph node like a normal node
# -------------------------------------------
#
# Create a node graph, add the group, set inputs, and run.

from node_graph import NodeGraph

g1 = NodeGraph(name="group_usage")
grp = g1.add_node(add_multiply, name="my_group")
g1.to_html()
