.. _node_graph:

===========================================
NodeGraph
===========================================
The :class:`~node_graph.NodeGraph` object is a collection of nodes and links.

Create a node graph
============================
- Create a empty node graph:

.. code-block:: python

    from node_graph import NodeGraph
    ng = NodeGraph(name="my_first_nodegraph")

- Add nodes:

.. code-block:: python

    float1 = ng.add_node("node_graph.float", name = "float1")
    add1 = ng.add_node("node_graph.test_add", name = "add1")

- Add link between nodes:

.. code-block:: python

    ng.add_link(float1.outputs[0], add1.inputs[0])

- Save to dict:

.. code-block:: python

    ng.to_dict()

List of all Methods
===================

.. autoclass:: node_graph.NodeGraph
   :members:
