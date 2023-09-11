
Welcome to NodeGraph's documentation!
===========================================

NodeGraph is an open-source platform for designing node-based workflows.

.. figure:: /_static/images/scinode-nodetree-introduction.png
   :width: 12cm

.. code-block:: python

    from node_graph import NodeGraph
    nt = NodeGraph(name="my_first_nodegraph")
    float1 = nt.nodes.new("TestFloat", value=2.0)
    float2 = nt.nodes.new("TestFloat", value=3.0)
    add1 = nt.nodes.new("TestAdd")
    nt.links.new(float1.outputs[0], add1.inputs[0])
    nt.links.new(float2.outputs[0], add1.inputs[1])


Installation
===========================================

The simplest way to install node_graph is to use pip.

.. code-block:: console

    pip install --upgrade --user node_graph


.. toctree::
   :maxdepth: 1
   :caption: Contents:

   quick_start
   concept/index
   yaml
   customize


Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
