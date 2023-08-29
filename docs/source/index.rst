
Welcome to NodeGraph's documentation!
===========================================

NodeGraph is an open-source platform for designing node-based workflows.

.. figure:: /_static/images/scinode-nodetree-introduction.png
   :width: 12cm

.. code-block:: python

    from node_graph import NodeGraph
    nt = NodeGraph(name="my_first_nodegraph")
    float1 = nt.nodes.new("Float", value=2.0)
    float2 = nt.nodes.new("Float", value=3.0)
    add1 = nt.nodes.new("Operator", operator="+")
    nt.links.new(float1.outputs[0], add1.inputs[0])
    nt.links.new(float2.outputs[0], add1.inputs[1])


.. toctree::
   :maxdepth: 1
   :caption: Contents:

   install/index
   quick_start
   concept/index
   yaml
   customize


Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
