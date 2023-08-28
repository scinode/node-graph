
Welcome to NodeGraph's documentation!
===========================================

NodeGraph is an open-source platform for designing node-based workflows.

.. figure:: /_static/images/scinode-nodetree-introduction.png
   :width: 12cm

.. code-block:: python

    from scinode import NodeTree
    nt = NodeTree(name="my_first_nodetree")
    float1 = nt.nodes.new("Float", value=2.0)
    float2 = nt.nodes.new("Float", value=3.0)
    add1 = nt.nodes.new("Operator", operator="+")
    nt.links.new(float1.outputs[0], add1.inputs[0])
    nt.links.new(float2.outputs[0], add1.inputs[1])

Getting Started
==================

   .. container::

         :doc:`install/index`

         :doc:`get_started/index`

         :doc:`tutorial/index`




.. toctree::
   :maxdepth: 1
   :caption: Contents:

   install/index
   get_started/index
   nodetree
   node/index
   collection
   property
   socket
   yaml
   develop/index
   faqs


Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
