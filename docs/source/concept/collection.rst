.. _connection:
.. module:: connection

============
Collection
============
The :class:`~node_graph.collection.Collection` object defines a collection of data. Collection properties can be added NodeTree and Task.


Data type
--------------
Collection can have different data type:

- :class:`~node_graph.collection.TaskCollection`
- :class:`~node_graph.collection.LinkCollection`
- :class:`~node_graph.collection.PropertyCollection`
- :class:`~node_graph.collection.InputSocketCollection`
- :class:`~node_graph.collection.OutputSocketCollection`


Task
----------------------------------------
:class:`~node_graph.collection.PropertyCollection`, :class:`~node_graph.collection.InputSocketCollection` and :class:`~node_graph.collection.OutputSocketCollection` belong to a :class:`~node_graph.task.Task`

For the output sockets, the length and order are important. It should be the same as the order of the results of the task executor.

.. code:: Python

    from node_graph.collection import (
        PropertyCollection,
        InputSocketCollection,
        OutputSocketCollection,)
    self.properties = PropertyCollection(self)
    self.inputs = InputSocketCollection(self)
    self.outputs = OutputSocketCollection(self)


Use
-----------
One can get a item by its name or index:

.. code:: Python

    # by name
    ng.tasks["Add task"].update_state()
    float1.properties["Float"].value = 2.0
    # by index
    ng.tasks[1].update_state()
    float1.properties[0].value = 2.0
    ng.add_link(float1.outputs[0], add1.inputs[0])



List of all Methods
----------------------

.. automodule:: node_graph.collection
   :members:
