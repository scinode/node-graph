.. _connection:
.. module:: connection

============
Collection
============
The :class:`~scinode.core.collection.Collection` object defines a collection of data. Collection properties can be added NodeTree and Node.


Data type
--------------
Collection can have different data type:

- :class:`~scinode.core.collection.NodeCollection`
- :class:`~scinode.core.collection.LinkCollection`
- :class:`~scinode.core.collection.PropertyCollection`
- :class:`~scinode.core.collection.InputSocketCollection`
- :class:`~scinode.core.collection.OutputSocketCollection`


NodeTree
----------------------------------------
:class:`~scinode.core.collection.NodeCollection` and :class:`~scinode.core.collection.LinkCollection` belong to a :class:`~scinode.nodetree.NodeTree`.

.. code:: Python

    from scinode.core.collection import NodeCollection, LinkCollection

    self.nodes = NodeCollection(self)
    self.links = LinkCollection(self)


Node
----------------------------------------
:class:`~scinode.core.collection.PropertyCollection`, :class:`~scinode.core.collection.InputSocketCollection` and :class:`~scinode.core.collection.OutputSocketCollection` belong to a :class:`~scinode.core.node.Node`

For the output sockets, the length and order are important. It should be the same as the order of the results of the node executor.

.. code:: Python

    from scinode.core.collection import (
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
    nt.nodes["Add node"].update_state()
    float1.properties["Float"].value = 2.0
    # by index
    nt.nodes[1].update_state()
    float1.properties[0].value = 2.0
    nt.links.new(float1.outputs[0], add1.inputs[0])



List of all Methods
----------------------

.. automodule:: scinode.core.collection
   :members:
