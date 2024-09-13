.. _connection:
.. module:: connection

============
Collection
============
The :class:`~node_graph.collection.Collection` object defines a collection of data. Collection properties can be added NodeTree and Node.


Data type
--------------
Collection can have different data type:

- :class:`~node_graph.collection.NodeCollection`
- :class:`~node_graph.collection.LinkCollection`
- :class:`~node_graph.collection.PropertyCollection`
- :class:`~node_graph.collection.InputSocketCollection`
- :class:`~node_graph.collection.OutputSocketCollection`


Node
----------------------------------------
:class:`~node_graph.collection.PropertyCollection`, :class:`~node_graph.collection.InputSocketCollection` and :class:`~node_graph.collection.OutputSocketCollection` belong to a :class:`~node_graph.node.Node`

For the output sockets, the length and order are important. It should be the same as the order of the results of the node executor.

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
    ng.nodes["Add node"].update_state()
    float1.properties["Float"].value = 2.0
    # by index
    ng.nodes[1].update_state()
    float1.properties[0].value = 2.0
    ng.links.new(float1.outputs[0], add1.inputs[0])



List of all Methods
----------------------

.. automodule:: node_graph.collection
   :members:
