from node_graph import NodeGraph, Node


def test_group_outputs(decorated_myadd_group):
    ng = NodeGraph(name="test_group_outputs")
    addgroup1 = ng.add_node(decorated_myadd_group, "addgroup1", y=9)
    # load from dict
    ndata = addgroup1.to_dict()
    addgroup2 = Node.from_dict(ndata)
    assert "result" in addgroup2.outputs
