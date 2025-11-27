from node_graph import Graph


def test_subgraph(decorated_myadd_group):
    sub_ng = decorated_myadd_group.build(x=1, y=2)
    ng = Graph(name="test_outputs")
    task1 = ng.add_task(sub_ng, "sub_ng", y=9)
    assert task1.name == "sub_ng"
    assert len(task1.tasks) == 6
    assert task1.inputs._value == {"y": 9}


def test_subgraph_link(decorated_myadd_group, decorated_myadd):
    sub_ng = decorated_myadd_group.build(x=1, y=2)
    ng = Graph(name="test_outputs")
    add1 = ng.add_task(decorated_myadd, "add1", x=2, y=3)
    task1 = ng.add_task(sub_ng, "sub_ng", x=add1.outputs.result, y=9)
    ng.add_task(decorated_myadd, "add2", x=2, y=task1.outputs.result)
    assert task1.name == "sub_ng"
    assert len(task1.tasks) == 6
    assert task1.inputs._value == {"y": 9}
