.. _control_flow_graph:

===========================================
Control flow graph
===========================================

Here we only introduce another concept of `Node`: control sockets.

.. figure:: /_static/images/node_with_control_entry_exit.png
   :width: 10cm


There are, two specially designated sockets: the entry socket, through which control enters into the flow graph, and the exit socket, through which all control flow leaves.

The entry socket will add the dependency to the node, and wait for execution.

The exit socket will jump to the next node in the nodetree, set the node to CREATE and wait for execution.

If node
===========

.. figure:: /_static/images/control_node_if.png
   :width: 5cm

For example, if we want to implement the following Python code:

.. code-block:: python

    a = 1
    if a > 0:
        b = a - 1
    else:
        b = a + 1
    add(b, 1)

The nodetree graph is as follows:

.. figure:: /_static/images/control_node_if_example.png
   :width: 15cm

The nodetree code is as follows:

.. code-block:: python

    from scinode import NodeTree
    nt = NodeTree(name="test_control_if")
    float1 = nt.nodes.new("TestFloat", "Float1")
    greater1 = nt.nodes.new("TestGreater", "greater1")
    greater1.set({"y": 0})
    float1.properties["value"].value = -2.0
    if1 = nt.nodes.new("If", "if1")
    add1 = nt.nodes.new("TestAdd", "add1")
    add1.set({"y": -1})
    add2 = nt.nodes.new("TestAdd", "add2")
    add2.set({"y": 1})
    select1 = nt.nodes.new("IfSelect", "select1")
    add3 = nt.nodes.new("TestAdd", "add3")
    add3.set({"y": 1})
    nt.links.new(float1.outputs[0], greater1.inputs[0])
    nt.links.new(greater1.outputs[0], if1.inputs[0])
    nt.links.new(float1.outputs[0], add1.inputs[0])
    nt.links.new(float1.outputs[0], add2.inputs[0])
    nt.links.new(if1.outputs[0], select1.inputs[0])
    nt.links.new(add1.outputs[0], select1.inputs[1])
    nt.links.new(add2.outputs[0], select1.inputs[2])
    nt.links.new(select1.outputs[0], add3.inputs[0])
    nt.ctrl_links.new(if1.ctrl_outputs["true"], add1.ctrl_inputs["entry"])
    nt.ctrl_links.new(if1.ctrl_outputs["false"], add2.ctrl_inputs["entry"])
    nt.ctrl_links.new(add1.ctrl_outputs[0], if1.ctrl_inputs["back"])
    nt.ctrl_links.new(add2.ctrl_outputs[0], if1.ctrl_inputs["back"])
    nt.ctrl_links.new(if1.ctrl_outputs["exit"], select1.ctrl_inputs["entry"])
    nt.launch()


For node
===========

.. figure:: /_static/images/control_node_for.png
   :width: 5cm


For example, if we want to implement the following Python code:

.. code-block:: python

    a = [1, 2, 3, 4, 5]
    b = 1
    result = []
    for x in a:
        c = x + 1
        result.append(c)
    s = sum(result)

The nodetree graph is as follows:

.. figure:: /_static/images/control_node_for_example.png
   :width: 15cm

The nodetree code is as follows:

.. code-block:: python

    from scinode import NodeTree

    nt = NodeTree(name="test_control_for_append")
    linspace1 = nt.nodes.new("Numpy", "linspace1")
    linspace1.set({"function": "linspace", "start": 1, "stop": 5, "num": 5})
    for1 = nt.nodes.new("For", "for1")
    add1 = nt.nodes.new("TestAdd", "add1")
    add1.set({"y": -1})
    np1 = nt.nodes.new("Numpy", "np1")
    np1.set({"function": "sum"})
    list1 = nt.nodes.new("List", "list1")
    append1 = nt.nodes.new("List", "append1")
    assign1 = nt.nodes.new("Assign", "assign1")
    append1.set({"function": "append"})
    nt.links.new(linspace1.outputs[0], for1.inputs[0])
    nt.links.new(for1.outputs[0], add1.inputs[0])
    nt.links.new(list1.outputs[0], append1.inputs[0])
    nt.links.new(add1.outputs[0], append1.inputs[1])
    nt.links.new(list1.outputs[0], assign1.inputs[0])
    nt.links.new(append1.outputs[0], assign1.inputs[1])
    nt.links.new(list1.outputs[0], np1.inputs[0])
    nt.ctrl_links.new(for1.ctrl_outputs["loop"], add1.ctrl_inputs["entry"])
    nt.ctrl_links.new(assign1.ctrl_outputs[0], for1.ctrl_inputs["iter"])
    nt.ctrl_links.new(for1.ctrl_outputs["jump"], np1.ctrl_inputs["entry"])
    nt.launch()

.. _Control-flow graph: https://en.wikipedia.org/wiki/Control-flow_graph
