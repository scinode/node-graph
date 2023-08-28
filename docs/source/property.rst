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

- :class:`~scinode.core.property.FloatProperty`
- :class:`~scinode.core.property.IntProperty`
- :class:`~scinode.core.property.BoolProperty`
- :class:`~scinode.core.property.StringProperty`
- :class:`~scinode.core.property.EnumProperty`
- :class:`~scinode.core.property.FloatVectorProperty`
- :class:`~scinode.core.property.IntVectorProperty`
- :class:`~scinode.core.property.BoolVectorProperty`

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

.. automodule:: scinode.core.property
   :members:

.. automodule:: scinode.properties.built_in
   :members:
