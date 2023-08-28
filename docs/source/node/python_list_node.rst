.. _python_list_node:

===========================================
List node
===========================================

List node includes the `list <https://docs.python.org/3/tutorial/datastructures.html>`_ data type and its methods.


List data
===========
Here is the normal Python code to create a list.

.. code-block:: python

    import numpy as np
    linspace1 = np.linspace(1, 3, 3)
    list1 = list(linspace1)

Here is the scinode code to create a list.

.. code-block:: python

    from scinode import NodeTree

    nt = NodeTree(name=f"test_list")
    linspace1 = nt.nodes.new("Numpy", "linspace1")
    linspace1.set({"function": "linspace", "start": 1, "stop": 3, "num": 3})
    list1 = nt.nodes.new("List", "list1")
    nt.links.new(linspace1.outputs[0], list1.inputs[0])





List methods
=============
Here is the normal Python code to append a value to a list.

.. code-block:: python

    list1.append(100)

Here is the scinode code to create a list.


.. code-block:: python

    list2 = nt.nodes.new("List", "list2")
    list2.set({"function": "Append", "Value": 100})
    # link output of list1 to input of list2,
    # so that list2 use list1 as input
    nt.links.new(list1.outputs[0], list2.inputs[0])
    # create a control link from list2 to list1,
    # so that list1 will be updated when list2 is finished
    nt.ctrl_links.new(list2.ctrl_outputs["Self"], list1.ctrl_inputs["Self"])



List of all Methods
===================

.. autoclass:: scinode.nodes.python_builtin.List
   :members:
