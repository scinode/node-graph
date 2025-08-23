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

   float1 = ng.add_node("node_graph.test_float")
   # set the value for Float property
   float1.properties["Float"].value = 2.0
   # or by
   float1.set_inputs({"Float": 2.0})


Create properties for a new Node
----------------------------------------

.. code:: Python

      def create_properties(self):
         self.add_property("FloatVector", "x", size=3, default=[0, 0, 0])

Add properties to a input socket
----------------------------------------

.. code:: Python

      def update_sockets(self):
         inp = self.add_input("node_graph.any", "x")
         inp.add_property("FloatVector", size=3, default=[0, 0, 0])

Assigning to Existing Node
--------------------------------

.. code:: Python

   node1 = ng.add_node(Node, "pow")
   node1.add_property("node_graph.float", "x")


Update Example
----------------
Support adding an ``update`` callback function when updating a property.

It can be useful to create a dynamic socket based on a property's value.

.. code:: Python

   # the item of the Enum options are [name, content, description]
   self.add_property("node_graph.enum",
                        "function",
                        default="cos",
                        options=[["cos", "cos", "cos function"],
                                 ["sin", "sin", "sin function"],
                                 ["pow", "pow", "pow function"]],
                        update=self.update_sockets,
                        )


List of all Methods
----------------------

.. automodule:: node_graph.property
   :members:

.. automodule:: node_graph.properties.built_in
   :members:
