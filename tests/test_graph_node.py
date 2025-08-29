from node_graph import NodeGraph


def test_build_graph(decorated_myadd_group):
    ng = decorated_myadd_group.build_graph(x=1, y=2)
    assert isinstance(ng, NodeGraph)
    assert len(ng.nodes) == 3
    assert len(ng.inputs) == 2
    assert len(ng.outputs) == 1
    assert len(ng.links) == 5


def test_run_as_a_node(decorated_myadd_group):
    ng = NodeGraph(name="test_outputs")
    addgroup1 = ng.add_node(decorated_myadd_group, "addgroup1", y=9)
    assert len(addgroup1.inputs) == 3  # 2 +  "_wait"
    assert len(addgroup1.outputs) == 3  # 1 + "_wait", "_outputs"
