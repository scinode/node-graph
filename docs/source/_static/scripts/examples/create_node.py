# Register the nodes
from scinode.utils.decorator import register_node

# MyFloat node
ndata = {
    "identifier": "MyFloat",
    "args": ["value"],
    "properties": [["Float", "value"]],
    "outputs": [["Float", "float"]],
    "executor": {"path": "builtins.float"},
}
register_node(ndata)
# MyAdd node
ndata = {
    "identifier": "MyAdd",
    "args": ["x", "y"],
    "inputs": [["Float", "x"], ["Float", "y"]],
    "outputs": [["General", "float"]],
    "executor": {"path": "numpy.add"},
}
register_node(ndata)
# create a nodetree
from scinode import NodeTree

nt = NodeTree(name="my_first_nodetree")
# add the first Float node, set the Float value
float1 = nt.nodes.new("MyFloat", "float1", value=2.0)
# add the second Float node.
float2 = nt.nodes.new("MyFloat", "float2", value=3.0)
# add the Add node.
add1 = nt.nodes.new("MyAdd", "add1")
# link the output sockets of Float nodes to the
# input sockets of Add node.
nt.links.new(float1.outputs[0], add1.inputs[0])
nt.links.new(float2.outputs[0], add1.inputs[1])
# launch the nodetree for running.
nt.launch()

import time

# wait 5 seconds for nodetree finished
time.sleep(5)
# update state of the nodetree
nt.update()
print("add1 state: ", add1.state)
print("add1 results: ", add1.results[0]["value"])
