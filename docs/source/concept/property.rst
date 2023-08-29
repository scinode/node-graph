.. _property:

============
Property
============
This module defines the properties of a Node. Property is a node data one can edit directly using a text editor, e.g. a string, a number or a combination of strings and numbers etc.


Data type
--------------

.. image:: /_static/images/property-type.png
   :width: 10cm
   :align: right

Property can have different data type:

- :class:`~node_graph.property.FloatProperty`
- :class:`~node_graph.property.IntProperty`
- :class:`~node_graph.property.BoolProperty`
- :class:`~node_graph.property.StringProperty`
- :class:`~node_graph.property.EnumProperty`
- :class:`~node_graph.property.FloatVectorProperty`
- :class:`~node_graph.property.IntVectorProperty`
- :class:`~node_graph.property.BoolVectorProperty`

One can extend the property type by designing a custom property. Please read :ref:`custom_property` page for how to create a custom property type.


Use
-----------

One can set the value of a property by:

.. code:: Python

   float1 = nt.nodes.new("TestFloat")
   # set the value for Float property
   float1.properties["Float"].value = 2.0
   # or by
   float1.set({"Float": 2.0})


Create properties for a new Node
----------------------------------------

.. code:: Python

      def create_properties(self):
         self.properties.new("FloatVector", "x", size=3, default=[0, 0, 0])

Add properties to a input socket
----------------------------------------

.. code:: Python

      def create_sockets(self):
         inp = self.inputs.new("General", "x")
         inp.add_property("FloatVector", size=3, default=[0, 0, 0])

Assigning to Existing Node
--------------------------------

.. code:: Python

   node1 = nt.nodes.new("ScinodeNode", "pow")
   node1.properties.new("Float", "x")


Update Example
----------------
Support adding an ``update`` callback function when updating a property.

It can be useful to create a dynamic socket based on a property's value.

.. code:: Python

   # the item of the Enum options are [name, content, description]
   self.properties.new("Enum",
                        "function",
                        default="cos",
                        options=[["cos", "cos", "cos function"],
                                 ["sin", "sin", "sin function"],
                                 ["pow", "pow", "pow function"]],
                        update=self.create_sockets,
                        )


List of all Methods
----------------------

.. automodule:: node_graph.property
   :members:

.. automodule:: node_graph.properties.built_in
   :members:
