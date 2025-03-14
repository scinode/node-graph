.. _node_group:

===========================================
Node Group
===========================================
Blender has a nice definition of Node Group, so I copied it below.

Conceptually, node groups allow you to treat a set of nodes as though it were just one node. They're similar to functions in programming: they can be reused and can be customized by changing their “parameters.” Grouping nodes can simplify a node tree by hiding away complexity and reusing repetitive parts.

Node groups can be nested (that is, node groups can contain other node groups). However, recursive node groups are prohibited for all the current node systems to prevent infinite recursion. A node group can never contain itself (or another group that contains it).

Here is a example. The node `Sqrt Add` is a node group, which consists three normal nodes (two `Sqrt` nodes and one `Add` node).

.. image:: /_static/images/node_group.png
   :width: 20cm

Define a node group
=====================
In order to define a new node group, one need to give the following informations:

- identifier.
- nodegraph. The data of node group is just like the data of a NodeGraph.
- exposing input and output sockets. When a node group is created, the group inputs and group outputs need to be defined to represent the data flow into and out of the group. This is done by defining the group inputs and outputs in the `inputs` and `outputs` fields of the node group data.
- exposing properties. The properties can also be exposed.

Decorator
-----------
One can define a node group using the `node.graph_builder` decorator. In the definition of the nodegraph, one can also set the default value for the node property.

.. code-block:: python

    from node_graph.decorator import node

    @node.graph_builder(identifier="MyAddGroup",
                outputs = [("add1.Result", "Result")],
    )
    def myaddgroup(x, y):
        from node_graph import NodeGraph
        ng = NodeGraph(name="NodeGroup")
        sqrt1 = ng.add_node("TestSqrt", "sqrt1")
        sqrt1.set({"t":2, "x": x})
        sqrt2 = ng.add_node("TestSqrt", "sqrt2")
        sqrt2.set({"x": y})
        add1 = ng.add_node("node_graph.test_add", "add1")
        ng.add_link(sqrt1.outputs[0], add1.inputs[0])
        ng.add_link(sqrt2.outputs[0], add1.inputs[1])
        return ng



Class
------------
One can define a nodegroup use a Node class, and specify the `node_type` to `GROUP`.

.. code-block:: python

    class TestSqrtAdd(Node):
        identifier: str = "TestSqrtAdd"
        name = "TestSqrtAdd"
        catalog = "Test"
        node_type: str = "GROUP"

        def get_default_node_group(self):
            from node_graph import NodeGraph
            ng = NodeGraph(name=self.name, uuid=self.uuid,
                        parent_node=self.uuid,
                        daemon_name=self.daemon_name)
            sqrt1 = ng.add_node("TestSqrt", "sqrt1")
            sqrt2 = ng.add_node("TestSqrt", "sqrt2")
            add1 = ng.add_node("node_graph.test_add", "add1")
            ng.add_link(sqrt1.outputs[0], add1.inputs[0])
            ng.add_link(sqrt2.outputs[0], add1.inputs[1])
            ng.group_properties = [("sqrt1", "t", "t1"),
                                    ("add1", "t", "t2"),]
            ng.group_inputs = [("sqrt1", "x", "x"),
                            ("sqrt2", "x", "y"),]
            ng.group_outputs = [("add1", "Result", "Result")]
            return ng


Execution
===============
A `node group` use a builtin executor. Run a `node group` will launch a new nodegraph use the data of the `node group`. The nodegraph's uuid is the same as the uuid of the `node group`. Some reference node will be added based on the group inputs. The results will be saved based on the group outputs.
