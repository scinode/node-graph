.. _property:

============
Property
============
This module defines the properties of a Task. Property is a task data one can edit directly using a text editor, e.g. a string, a number or a combination of strings and numbers etc.


Data type
--------------

.. image:: /_static/images/property-type.png
   :width: 10cm
   :align: right

Property can have different data type:

- :class:`~node_graph.properties.builtins.PropertyFloat`
- :class:`~node_graph.properties.builtins.PropertyInt`
- :class:`~node_graph.properties.builtins.PropertyBool`
- :class:`~node_graph.properties.builtins.PropertyString`
- :class:`~node_graph.properties.builtins.PropertyEnum`
- :class:`~node_graph.properties.builtins.PropertyFloatVector`
- :class:`~node_graph.properties.builtins.PropertyIntVector`
- :class:`~node_graph.properties.builtins.PropertyBoolVector`

One can extend the property type by designing a custom property. Please read :ref:`custom_property` page for how to create a custom property type.


Use
-----------

One can set the value of a property by:

.. code:: Python

   float1 = ng.add_task("node_graph.test_float")
   # set the value for Float property
   float1.properties["Float"].value = 2.0
   # or by
   float1.set_inputs({"Float": 2.0})

Validation and wrapped values
--------------------------------

Each property type declares ``allowed_types`` and values are validated when assigned.

In some runtimes, you may store values using wrapper objects (for example an ORM data node that exposes a Python value via ``.value``).
To support this without hardcoding third-party dependencies, ``TaskProperty.validate`` accepts a value if any of these match ``allowed_types``:

- the value itself
- ``value.__wrapped__`` (if present)
- ``value.value`` (if present)
- values returned by any registered validation adapters

External packages (e.g. an engine) can register adapters globally:

.. code:: Python

   from node_graph.property import TaskProperty

   def unwrap_custom(value):
       if hasattr(value, "get_list") and callable(value.get_list):
           return value.get_list()
       return TaskProperty.NOT_ADAPTED

   TaskProperty.register_validation_adapter(unwrap_custom)


Create properties for a new Task
----------------------------------------

.. code:: Python

      def create_properties(self):
         self.add_property("node_graph.float_vector", "x", size=3, default=[0, 0, 0])

Add properties to a input socket
----------------------------------------

.. code:: Python

      def update_spec(self):
         inp = self.add_input("node_graph.any", "x")
         inp.add_property("node_graph.float_vector", size=3, default=[0, 0, 0])

Assigning to Existing Task
--------------------------------

.. code:: Python

   task1 = ng.add_task(Task, "pow")
   task1.add_property("node_graph.float", "x")


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
                        update=self.update_spec,
                        )


List of all Methods
----------------------

.. automodule:: node_graph.property
   :members:

.. automodule:: node_graph.properties.builtins
   :members:
