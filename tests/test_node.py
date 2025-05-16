from node_graph import NodeGraph, NodePool
from node_graph.node import Node


def test_base_node():
    """Create a node.
    Append it to a nodegraph.
    """
    ng = NodeGraph(name="test_base_node")
    n = Node.new(NodePool.node_graph.test_float)
    # added to nodegraph
    ng.append_node(n)
    assert n.graph == ng
    # copy
    n1 = n.copy(name="n1")
    assert n1.graph == ng
    assert n1.name == "n1"


def test_id_name():

    ng = NodeGraph(name="test_id_name")
    # auto generate name for the node
    math1 = ng.add_node(NodePool.node_graph.test_add)
    assert math1.name == "test_add"
    math2 = ng.add_node(NodePool.node_graph.test_add)
    assert math2.name == "test_add1"
    # set node name manually
    math3 = ng.add_node(NodePool.node_graph.test_add, name="Math3")
    assert math3.name == "Math3"


def test_set_node_as_input():
    ng = NodeGraph(name="test_set_inputs")
    add1 = ng.add_node(NodePool.node_graph.test_add, "add1")
    add2 = ng.add_node(NodePool.node_graph.test_add, "add2")
    add2.set({"x": add1})
    assert len(ng.links) == 1
    assert add2.inputs["x"].property.value is None


def test_set_link_as_input():
    ng = NodeGraph(name="test_set_inputs")
    add1 = ng.add_node(NodePool.node_graph.test_add, "add1")
    add2 = ng.add_node(NodePool.node_graph.test_add, "add2")
    add2.set({"x": add1.outputs["result"]})
    assert len(ng.links) == 1
    assert add2.inputs["x"].property.value is None


def test_set_non_exit_input_for_dynamic_input():
    node = Node()
    node.inputs._metadata.dynamic = True
    node.set({"x": 1})
    assert node.inputs.x.value == 1


def test_set_property():

    ng = NodeGraph(name="test_set_property")
    math = ng.add_node(NodePool.node_graph.test_add, "Math")
    math.inputs["x"].property.value = 2
    assert math.inputs["x"].property.value == 2


def test_to_dict():

    ng = NodeGraph(name="test_to_dict")
    math = ng.add_node(NodePool.node_graph.test_add, "Math")
    math.inputs["x"].property.value = 2
    data = math.to_dict()
    assert data["identifier"] == "node_graph.test_add"


def test_copy():
    """Copy node.

    All the properties and sockets should be copied.

    """

    ng = NodeGraph(name="test_copy")
    math = ng.add_node(NodePool.node_graph.test_add, "Math", t=5, x=2)
    math1 = math.copy()
    assert math1.properties["t"].value == 5
    assert math1.inputs["x"].property.value == 2
    assert math1.graph.uuid == ng.uuid
    assert math1.name == f"{math.name}_copy"
    #
    ng.append_node(math1)
    assert len(ng.nodes) == 2


def test_check_name():
    """Check name when creating a node."""
    ng = NodeGraph(name="test_check_name")
    ng.add_node(NodePool.node_graph.test_add, "add1")
    # check if it raises an error if the name is already taken
    try:
        ng.add_node(NodePool.node_graph.test_add, "add1")
    except ValueError as e:
        assert str(e) == "add1 already exists, please choose another name."
    else:
        raise AssertionError("Name already exists.")

    try:
        ng.add_node("node_graph.test_ad", "add2")
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
    ng.add_node(NodePool.node_graph.test_add, "add1")
    assert repr(ng.nodes) == 'NodeCollection(parent = "test_repr", nodes = ["add1"])'


def test_nodegraph_node():
    ng = NodeGraph(name="test_nodegraph_node")
    sub_ng = NodeGraph(name="sub_nodegraph")
    sub_ng.add_node(NodePool.node_graph.test_add, "add1")
    sub_ng.add_node(
        NodePool.node_graph.test_add, "add2", x=sub_ng.nodes.add1.outputs.result
    )
    ng.add_node(sub_ng, "sub_ng")
    assert len(ng.nodes) == 1
    assert len(ng.nodes.sub_ng.nodes) == 2
    assert len(ng.nodes.sub_ng.links) == 1
    assert "add1" in ng.nodes.sub_ng.nodes
    # check intpus
    assert "add1" in ng.nodes.sub_ng.inputs
    assert "add1.x" in ng.nodes.sub_ng.inputs
    assert "add1.result" in ng.nodes.sub_ng.outputs
    assert set(ng.nodes.sub_ng.inputs._get_all_keys()) == {
        "add1",
        "add2",
        "_wait",
        "add1.x",
        "add1.y",
        "add2.x",
        "add2.y",
    }
    assert set(ng.nodes.sub_ng.outputs._get_all_keys()) == {
        "add1",
        "add2",
        "_outputs",
        "_wait",
        "add1._outputs",
        "add1.result",
        "add2._outputs",
        "add2.result",
    }


def test_execute(decorated_myadd):
    result = decorated_myadd(1, 2)
    result = result._node.execute()
