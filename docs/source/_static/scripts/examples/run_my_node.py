from scinode import NodeTree
from custom_node import float_node, add_node
import time

# create a nodetree
nt = NodeTree(name="create_node")
# add the first Float node. set the Float value
float1 = nt.nodes.new(float_node.identifier, "float1", value=2.0)
# add the second Float node.
float2 = nt.nodes.new(float_node.identifier, "float2", value=3.0)
# add the Add node.
add1 = nt.nodes.new(add_node.identifier, "add1")
# link the output sockets of Float nodes to the
# input sockets of Add node.
nt.links.new(float1.outputs[0], add1.inputs[0])
nt.links.new(float2.outputs[0], add1.inputs[1])
# launch the nodetree for running.
nt.launch()
# wait 5 seconds for the job to be finished.
time.sleep(5)
# update the state and results of the nodetree
nt.update()
# pow1 and sqrt1 have one output socket, so we read results[0]
print("Result of pow1: ", add1.results[0]["value"])
