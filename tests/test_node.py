from node_graph import NodeGraph
from node_graph.node import Node


def test_base_node():
    """Create a node.
    Append it to a nodegraph.
    """
    nt = NodeGraph(name="test_base_node")
    n = Node.new("TestFloat")
    # added to nodegraph
    nt.nodes.append(n)
    assert n.parent == nt
    # copy
    n1 = n.copy(name="n1")
    assert n1.parent == nt
    assert n1.name == "n1"


def test_id_name():

    nt = NodeGraph(name="test_id_name")
    # auto generate name for the node
    math1 = nt.nodes.new("TestAdd")
    assert math1.inner_id == 1
    assert math1.name == "TestAdd1"
    # set node name manually
    math2 = nt.nodes.new("TestAdd", "Math2")
    assert math2.inner_id == 2
    assert math2.name == "Math2"
    math3 = nt.nodes.new("TestAdd", name="Math3")
    assert math3.name == "Math3"
    assert math3.inner_id == 3


def test_set_property():

    nt = NodeGraph(name="test_set_property")
    math = nt.nodes.new("TestAdd", "Math")
    math.inputs["x"].property.value = 2
    assert math.inputs["x"].property.value == 2


def test_to_dict():

    nt = NodeGraph(name="test_to_dict")
    math = nt.nodes.new("TestAdd", "Math")
    math.inputs["x"].property.value = 2
    data = math.to_dict()
    assert data["metadata"]["identifier"] == "TestAdd"


def test_copy():
    """Copy node.

    All the properties and sockets should be copied.

    """

    nt = NodeGraph(name="test_copy")
    math = nt.nodes.new("TestAdd", "Math", t=5, x=2)
    math1 = math.copy()
    assert math1.properties["t"].value == 5
    assert math1.inputs["x"].property.value == 2
    assert math1.parent.uuid == nt.uuid
    assert math1.name == f"{math.name}_copy"
    #
    nt.nodes.append(math1)
    assert len(nt.nodes) == 2
