"""
Node graph
==========

The :class:`node_graph.NodeGraph` object is a collection of nodes and links.
This example shows how to create a node graph, add nodes and links,
and export it to a dictionary.
"""

# %%
# Create a node graph
# -------------------
#
# Create an empty node graph.

from node_graph import NodeGraph

ng = NodeGraph(name="my_first_nodegraph")

# %%
# Add nodes
# ---------
#
# Add a `float` node and an `add` node.

float1 = ng.add_node("node_graph.test_float", name="float1")
add1 = ng.add_node("node_graph.test_add", name="add1")

# %%
# Add link between nodes
# ----------------------
#
# Connect the output of ``float1`` to the input of ``add1``.

ng.add_link(float1.outputs.float, add1.inputs.x)

ng.to_html()
# %%
# Save to dict
# ------------
#
# Convert the node graph to a Python dictionary representation.

d = ng.to_dict()
print("NodeGraph as dict:")
print(d)

# %%
# API reference
# -------------
#
# In the narrative documentation you can include an API reference:
#
# .. autoclass:: node_graph.NodeGraph
#    :members:
