.. _python_operator_node:

===========================================
Operator node
===========================================

Operator node includes all the methods of the `operator <https://docs.python.org/3/library/operator.html>`_ module.


Arithmetic Operators
====================
Here is the normal Python code to add two number.

.. code-block:: python

    3 + 2

Here is the scinode code.

.. code-block:: python

    from scinode import NodeTree

    nt = NodeTree(name=f"test_operator_add")
    operator1 = nt.nodes.new("Operator", "operator1")
    operator1.set({"operator": "+", "x": 3, "y": 2})


Assignment Operators
=====================


Comparison Operators
=====================

.. code-block:: python

    operator1.set({"operator": ">", "x": 3, "y": 2})




List of all Methods
===================

.. autoclass:: scinode.nodes.python_builtin.Operator
   :members:
