from node_graph import NodeGraph
from node_graph.node import Node


def test_base_node():
    """Create a node.
    Append it to a nodegraph.
    """
    ng = NodeGraph(name="test_base_node")
    n = Node.new("node_graph.test_float")
    # added to nodegraph
    ng.nodes.append(n)
    assert n.parent == ng
    # copy
    n1 = n.copy(name="n1")
    assert n1.parent == ng
    assert n1.name == "n1"


def test_id_name():

    ng = NodeGraph(name="test_id_name")
    # auto generate name for the node
    math1 = ng.nodes.new("node_graph.test_add")
    assert math1.list_index == 1
    assert math1.name == "test_add1"
    # set node name manually
    math2 = ng.nodes.new("node_graph.test_add", "Math2")
    assert math2.list_index == 2
    assert math2.name == "Math2"
    math3 = ng.nodes.new("node_graph.test_add", name="Math3")
    assert math3.name == "Math3"
    assert math3.list_index == 3


def test_set_property():

    ng = NodeGraph(name="test_set_property")
    math = ng.nodes.new("node_graph.test_add", "Math")
    math.inputs["x"].property.value = 2
    assert math.inputs["x"].property.value == 2


def test_to_dict():

    ng = NodeGraph(name="test_to_dict")
    math = ng.nodes.new("node_graph.test_add", "Math")
    math.inputs["x"].property.value = 2
    data = math.to_dict()
    assert data["identifier"] == "node_graph.test_add"


def test_copy():
    """Copy node.

    All the properties and sockets should be copied.

    """

    ng = NodeGraph(name="test_copy")
    math = ng.nodes.new("node_graph.test_add", "Math", t=5, x=2)
    math1 = math.copy()
    assert math1.properties["t"].value == 5
    assert math1.inputs["x"].property.value == 2
    assert math1.parent.uuid == ng.uuid
    assert math1.name == f"{math.name}_copy"
    #
    ng.nodes.append(math1)
    assert len(ng.nodes) == 2


def test_check_name():
    """Check name when creating a node."""
    ng = NodeGraph(name="test_check_name")
    ng.nodes.new("node_graph.test_add", "add1")
    # check if it raises an error if the name is already taken
    try:
        ng.nodes.new("node_graph.test_add", "add1")
    except ValueError as e:
        assert str(e) == "add1 already exists, please choose another name."
    else:
        raise AssertionError("Name already exists.")

    try:
        ng.nodes.new("node_graph.test_ad", "add2")
    except ValueError as e:
        assert (
            "Identifier: node_graph.test_ad is not defined. Did you mean node_graph.test_add"
            in str(e)
        )
    else:
        raise AssertionError("Name already exists.")


def test_repr():
    """Test __repr__ method."""
    ng = NodeGraph(name="test_repr")
    ng.nodes.new("node_graph.test_add", "add1")
    assert repr(ng.nodes) == 'NodeCollection(parent = "test_repr", nodes = ["add1"])'
