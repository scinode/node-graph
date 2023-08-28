from scinode import NodeTree

nt = NodeTree(name="my_first_nodetree")
float1 = nt.nodes.new("TestFloat", "float1", value=2.0)
float2 = nt.nodes.new("TestFloat", "float2", value=3.0, t=5)
add1 = nt.nodes.new("TestAdd", "add1")
nt.links.new(float1.outputs[0], add1.inputs[0])
nt.links.new(float2.outputs[0], add1.inputs[1])
nt.launch()
