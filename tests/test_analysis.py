from node_graph.analysis import ConnectivityAnalysis, DifferenceAnalysis
from node_graph import NodePool


def test_connectivity(ng):
    # Test that the graph is connected
    ngdata = ng.to_dict()
    nc = ConnectivityAnalysis(ngdata)
    connectivity = nc.build_connectivity()
    assert connectivity["child_node"]["float1"] == ["add1", "add2"]
    assert connectivity["child_node"]["add1"] == ["add2"]


def test_difference(ng):
    # Test that the graph is connected
    ngdata1 = ng.to_dict()
    ng.add_node(NodePool.node_graph.test_add, "add3")
    ng.nodes.add1.set({"x": 5})
    ngdata2 = ng.to_dict()
    da = DifferenceAnalysis(ng1=ngdata1, ng2=ngdata2)
    (new_tasks, modified_tasks, _) = da.build_difference()
    assert new_tasks == set(["add3"])
    assert modified_tasks == set(["add1"])
