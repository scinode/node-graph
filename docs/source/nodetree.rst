.. _nodetree:

===========================================
Nodetree
===========================================
The :class:`~scinode.core.nodetree.NodeTree` object is a collection of nodes and links.

Create and launch nodetree
============================
- Create a empty nodetree:

.. code-block:: python

    from scinode import NodeTree
    nt = NodeTree(name="my_first_nodetree")

- Add nodes:

.. code-block:: python

    float1 = nt.nodes.new("Float", name = "float1")
    add1 = nt.nodes.new("TestAdd", name = "add1")

- Add link between nodes:

.. code-block:: python

    nt.links.new(float1.outputs[0], add1.inputs[0])

- Launch the nodetree:

.. code-block:: python

    nt.launch()

Control link
================
Control link is a special link, which is used by a node to control the execution and data of other nodes. For example, the ``If`` node has two control outputs, ``True`` and ``False``, which can be used to control the execution of other nodes.

.. code-block:: python

    nt.ctrl_links.new(if1.ctrl_outputs["True"], add1.ctrl_inputs["Entry"])
    nt.ctrl_links.new(if1.ctrl_outputs["False"], add2.ctrl_inputs["Entry"])

Execute order
===============
The nodes will be executed when:

- No input node
- All input nodes finish.

.. figure:: /_static/images/nodetree-execute.gif
   :width: 20cm

Working mode
===============
SciNode supports the following working modes:


- Normal launch.
- Reset, and launch a new workflow.
- Add new nodes, and continue the workflow.
- Add new nodes, and start a new workflow.
- modify nodes, and restart workflow after the node
- modify nodes, and start a new workflow
- pause the node and the following nodes, when a job fails.
- modify the failed node, continue the workflow
- pause the node manually, and play it again.


Reset node
------------
Resetting a node will also reset all its child nodes.

.. figure:: /_static/images/nodetree-reset.gif
   :width: 20cm

Add new nodes
--------------
Add new nodes, and continue the workflow:

.. figure:: /_static/images/nodetree-add-continue.gif
   :width: 20cm

The above modes can be achieved by the Python script, the GUI, or the command line.

List of all Methods
===================

.. autoclass:: scinode.core.nodetree.NodeTree
   :members:
