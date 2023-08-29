.. _socket:

============
Socket
============
Sockets are used to indicate the type of data that can be transferred from one node to another. You can only connect the inputs and outputs with the same socket type.

.. image:: /_static/images/socket.png
   :width: 12cm
   :align: right

Location
--------------

According to its location, there are two kind of sockets:

- Input
- Output

Data type
--------------
Socket can have different data type:

- :class:`~node_graph.socket.SocketFloat`
- :class:`~node_graph.socket.SocketInt`
- :class:`~node_graph.socket.SocketBool`
- :class:`~node_graph.socket.SocketString`
- :class:`~node_graph.socket.SocketGeneral`

One can extend the socket type by designing a custom socket. Please read :ref:`custom_socket` page for how to create a custom socket type.


Property
-----------
Socket has a property, which is used to store the data. The data can be used when there is no connection to the input socket. The property is a :class:`~node_graph.property.Property` object. The property can be added when define a custom socket. Or it can be added later by using ``add_property`` method for the :class:`~node_graph.socket.SocketGeneral`.

.. code:: Python

   def create_sockets(self):
      # create a General socket.
      inp = self.inputs.new("General", "symbols")
      # add a string property to the socket with default value "H".
      inp.add_property("String", "default", default="H"})

Serialization
----------------
Socket has serialization/deserialization methods, which tell how the results stored and read from the database.

There are two built_in serialization methods:

- `None`, No serialization. This is used for the Python base type (Int, Float, Bool, String).
- `Pickle`, this is used in for the :class:`~node_graph.socket.SocketGeneral`

User can define a new socket type with a customized serialization method.

Dynamic socket
-----------------
User can update the sockets based on a property value (use ``udpate`` callback). Please read :ref:`dynamic_socket` page for how to create dynamic sockets.


List of all Methods
--------------------

.. automodule:: node_graph.socket
   :members:

.. automodule:: node_graph.sockets.built_in
   :members:
