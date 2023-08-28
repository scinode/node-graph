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
- control input and output sockets (optional)
- executor: a function (class) to process node data.
- belong to a `Nodetree`


Metadata
====================
- `identifier`: identifier of this node class.
- `name`: name of this node.

.. code-block:: python

   # identifier: TestFloat, name: float1
   node1 = nt.nodes.new("TestFloat", "float1")
   node2 = nt.nodes.new("TestFloat", "float2")

- State
   A node can has following states:
   ``CREATED``, ``RUNNING``, ``FINISHED``, ``FAILED``, ``CANCELLED``, ``PAUSED``, ``WAITING``, ``SKIPPED``, ``UNKNOWN``.

- Action
   Actions applied to a node:
   ``NONE``,  ``LAUNCH``,  ``WAIT_RESULT``,  ``PAUSE``,  ``PLAY``,  ``GATHER``,  ``CANCEL``,  ``SKIP``.

Executor
===========================================
Finally, the main entry point is the executor. An executor is a Python class/function for processing node data. It uses the node properties, inputs, outputs and context information as arguments (positional and keyword).

- function
- class

.. note::

   One can run nodetree inside a executor, and in this way, one can create nodes dynamically base on the results of other nodes.


Classification
==================

According to the purpose of the node:

- Data
- Process
- Control

In principle, a node is unit which process input data and output results. However, base on the purpose of the node, we can define some node ase “data” node.
Data node is the node for a data type, e.g. int, float, list, dict. It should has a Input socket. If there is not link to the input, the value of the property of the socket will be used.


According to the state of the node:

- Normal
- Reference
- Copy
- Group

According to the execution:

- Passive
- Active. An active node has a control loop that runs in its own process or thread.




Use Node
==================
Create a Node inside a NodeTree

.. code-block:: python

   from scinode import NodeTree

   # create a nodetree
   nt = NodeTree(name="test_node")
   # create a node using the Node identifier, e.g. TestFloat
   float1 = nt.nodes.new("TestFloat")
   # set node properties
   float1.set({"Float": 8})
   # copy a node
   float2 = float1.copy()
   # append a node to the nodetree
   nt.nodes.append(float2)

Load node from database

.. code-block:: python

   from scinode.core.node import Node

   # load a Node from database
   uuid = "xxx"
   node = Node.load(uuid)

.. note::

   One can not edit the node and save it to database directly. All the changes should be saved using the `NodeTree` object.

   >>> nt.save()


Define and register a custom Node
===================================

Decorator
------------
One can use a decorator to register a function as a `Node`. The decorator will automatically create a `Node` which uses the function as its executor, and then add the created `Node` to the node list.

In your `~/.scinode/custom_node/custom_node.py` file, add the following code:

.. code-block:: python

   from scinode.utils.decorator import node
   # register a function as a node.
   # One need to specify the identifier, args, properties, inputs, outputs
   @node(
      identifier="MyAdd",
      args=["t", "x", "y"],
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

.. note::

   The decorator will only register the function to the `Node` list when the module containing the decorator is imported. It will not automatically search all Python packages. If the decorator is used in multiple modules or packages, it will only register the function in the module where it is actually imported and used.

Restart your daemon, and then you can use the node in a nodetree:

.. code-block:: python

   # then one can use the node in a nodetree
   from scinode import NodeTree
   from custom_node import myadd
   import time

   nt = NodeTree(name="test_decorator")
   # here we use the myadd.identifier to specify the node type
   add1 = nt.nodes.new(myadd.identifier, "add1")
   add1.set({"x": 8})
   nt.launch()
   time.sleep(5)
   print("add1.result: ", add1.results[0]["value"])

.. note::

   Unfortunately, both builtin daemon and the Celery work does not suport the auto-reload option. Therefore, one has to restart the daemon manually when you add new nodes using decorator or change the code of the decoratored nodes.


class
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

List of all Methods
===================

.. autoclass:: scinode.core.node.Node
   :members:
