"""
Graph
==========

The :class:`node_graph.Graph` object is a collection of tasks and links.
This example shows how to create a graph, add tasks and links,
and export it to a dictionary.
"""

# %%
# Create a graph
# -------------------
#
# Create an empty graph.

from node_graph import Graph

g = Graph(name="my_first_nodegraph")

# %%
# Add nodes
# ---------
#
# Add a `float` task and an `add` task.

float1 = g.add_task("node_graph.test_float", name="float1")
add1 = g.add_task("node_graph.test_add", name="add1")

# %%
# Add link between nodes
# ----------------------
#
# Connect the output of ``float1`` to the input of ``add1``.

g.add_link(float1.outputs.result, add1.inputs.x)

g.to_html()
# %%
# Save to dict
# ------------
#
# Convert the graph to a Python dictionary representation.

d = g.to_dict()
print("Graph as dict:")
print(d)
