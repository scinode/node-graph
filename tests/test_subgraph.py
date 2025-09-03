from node_graph import NodeGraph


def test_subgraph(decorated_myadd_group):
    sub_ng = decorated_myadd_group.build_graph(x=1, y=2)
    ng = NodeGraph(name="test_outputs")
    node1 = ng.add_node(sub_ng, "sub_ng", y=9)
    assert node1.name == "sub_ng"
    assert len(node1.nodes) == 6
    assert node1.inputs._value == {"y": 9}


def test_subgraph_link(decorated_myadd_group, decorated_myadd):
    sub_ng = decorated_myadd_group.build_graph(x=1, y=2)
    ng = NodeGraph(name="test_outputs")
    add1 = ng.add_node(decorated_myadd, "add1", x=2, y=3)
    node1 = ng.add_node(sub_ng, "sub_ng", x=add1.outputs.result, y=9)
    ng.add_node(decorated_myadd, "add2", x=2, y=node1.outputs.result)
    assert node1.name == "sub_ng"
    assert len(node1.nodes) == 6
    assert node1.inputs._value == {"y": 9}
