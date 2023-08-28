.. _control_node:

===========================================
Control nodes
===========================================
An ordinary node run independently, thus will not affect other nodes. However, some special nodes, called control nodes, will interfere with other nodes. One can think of them as the flow control statements known from Python languages, e.g. ``for``, ``if``, ``break``.

We can use these nodes for a more complicated workflow.



Switch
------------
Run the nodes after Switch node if input ``Switch`` socket is ``True``, otherwise does not executed the following nodes.

.. image:: /_static/images/control_switch_node.png
   :width: 15cm




Update
----------
Update node will update the input socket and run the workflow again.

.. image:: /_static/images/control_update_node.png
   :width: 15cm

Scatter
--------------
In the following schematic,the ``Result`` socket of node 1 has a list of value: [a, b, c]. We want to run the node 2 and the following nodes with input ``a``, ``b`` and ``c`` separately. The Scatter node will generate a series of data node with the output as ``a``, ``b`` and ``c`` respectively.

.. image:: /_static/images/scatter_node_1.png
   :width: 15cm


The scatter node will generate a serierl of sub-nodetree. And the input of the first node will be the result at the index.

.. image:: /_static/images/scatter_node_2.png
   :width: 12cm


List of all Methods
===================

.. automodule:: scinode.nodes.control
   :members:
