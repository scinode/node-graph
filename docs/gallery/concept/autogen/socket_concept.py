"""
Socket
======

Sockets are used to indicate the type of data that can be transferred
from one node to another. You can only connect inputs and outputs with
the same socket type.
"""

# %%
# Location
# --------
#
# According to its location, there are two kinds of sockets:
#
# - Input
# - Output
#
# Each node can have input sockets and output sockets.

from node_graph import NodeGraph

ng = NodeGraph(name="socket_example")
float1 = ng.add_node("node_graph.test_float", name="float1")
float2 = ng.add_node("node_graph.test_float", name="float2")

# connect output of float1 to input of float2
ng.add_link(float1.outputs.result, float2.inputs.value)

# %%
# Data type
# ---------
#
# Socket can have different data types:
#
# - ``SocketFloat``
# - ``SocketInt``
# - ``SocketBool``
# - ``SocketString``
# - ``SocketAny``
#
# One can extend the socket type by designing a custom socket
# (see the :ref:`custom_socket` page in the docs).


# %%
# Property
# --------
#
# A socket has a property, which stores the data when there is no connection
# to the input socket. The property is a :class:`node_graph.property.Property`
# object. You can add properties when defining a custom socket or later with
# ``add_property`` for ``SocketAny``.

from node_graph.node import Node


class SymbolNode(Node):
    identifier = "SymbolNode"
    name = "SymbolNode"

    def update_spec(self):
        # create an Any type socket
        inp = self.add_input("node_graph.any", "symbols")
        # add a string property to the socket with default value "H"
        inp.add_property("node_graph.string", "default", default="H")


node = SymbolNode(parent=ng)
print("Custom node with Any socket and property:", node.inputs.symbols.value)

# %%
# Serialization
# -------------
#
# Sockets support serialization and deserialization, which determine how results
# are stored and read from the database.
#
# There are two built-in serialization methods:
#
# - ``None``: no serialization, used for base types (Int, Float, Bool, String).
# - ``Json``: JSON serialization, used for complex types (e.g. lists, dicts).
#
# Users can define a new socket type with a custom serialization method.


# %%
# Dynamic sockets
# ---------------
#
# Users can update sockets dynamically based on a property value
# using an ``update`` callback. For details, see the :ref:`dynamic_socket`
# page in the documentation.
