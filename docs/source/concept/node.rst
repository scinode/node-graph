.. _node_concept:

===========================================
Node
===========================================

Here we only introduce the general features of `Node`.

.. figure:: /_static/images/node.png
   :width: 15cm

A node can have the following features:

- metadata, e.g. name, state, type
- properties (optional)
- input and output sockets (optional)
- executor: a function (class) to process node data.


Metadata
====================
- `identifier`: identifier of this node class.
- `name`: name of this node.

.. code-block:: python

   # identifier: TestFloat, name: float1
   node1 = nt.nodes.new("TestFloat", name="float1")
   node2 = nt.nodes.new("TestFloat", name="float2")

Executor
===========================================
An executor is a Python class/function for processing node data. It uses the node properties, inputs, outputs and context information as arguments (positional and keyword).

- function
- class



Define and register a custom Node
===================================

Decorator
------------
One can use a decorator to register a function as a `Node`. The decorator will automatically create a `Node` which uses the function as its executor, and then add the created `Node` to the node list.


.. code-block:: python

   from node_graph.utils.decorator import node
   # register a function as a node.
   # One need to specify the identifier, args, properties, inputs, outputs
   @node(
      identifier="MyAdd",
      properties=[["Float", "t", {"default": 2}]],
      inputs=[
         ["Float", "x", ["Float", {"default": 2}]],
         ["Float", "y", ["Float", {"default": 3}]],
         ],
      outputs=[["Float", "Result"]],
   )
   def myadd(t, x, y):
      import time
      time.sleep(t)
      return x + y

then you can use the node in a nodegraph:

.. code-block:: python

   # then one can use the node in a nodegraph
   from node_graph import NodeGraph
   from custom_node import myadd
   import time

   nt = NodeGraph(name="test_decorator")
   # here we use the myadd
   add1 = nt.nodes.new(myadd, "add1")
   add1.set({"x": 8})
   nt.launch()
   time.sleep(5)
   print("add1.result: ", add1.results[0]["value"])


Class
-----------
One can define a new node by extend the `Node` class.

.. code-block:: python

   class TestAdd(Node):
      """TestAdd

      Inputs:
         t (int): delay time (s).
         x (float):
         y (float):

      Outputs:
         Result (float).

      """

      identifier: str = "TestAdd"
      name = "TestAdd"
      catalog = "Test"
      kwargs = ["t", "x", "y"]

      def create_properties(self):
         self.properties.new("Int", "t", default=1)

      def create_sockets(self):
         self.inputs.clear()
         self.outputs.clear()
         self.inputs.new("Float", "x")
         self.inputs.new("Float", "y")
         self.outputs.new("Float", "Result")

      def get_executor(self):
         return {
               "path": "scinode.executors.test",
               "name": "test_add",
         }


Use Node
==================
Create a Node inside a NodeGraph

.. code-block:: python

   from node_graph import NodeGraph

   # create a nodegraph
   nt = NodeGraph(name="test_node")
   # create a node using the Node identifier, e.g. TestFloat
   float1 = nt.nodes.new("TestFloat")
   # set node properties
   float1.set({"Float": 8})
   # copy a node
   float2 = float1.copy()
   # append a node to the nodegraph
   nt.nodes.append(float2)

Load node from database

.. code-block:: python

   from node_graph.core.node import Node

   # load a Node from database
   uuid = "xxx"
   node = Node.load(uuid)

.. note::

   One can not edit the node and save it to database directly. All the changes should be saved using the `NodeGraph` object.

   >>> nt.save()


List of all Methods
===================

.. autoclass:: node_graph.node.Node
   :members:
