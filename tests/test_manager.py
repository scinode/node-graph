from node_graph.manager import active_graph, get_current_graph, set_current_graph
from node_graph import NodeGraph


def test_manager():

    ng1 = NodeGraph("ng1")
    set_current_graph(ng1)
    assert get_current_graph() == ng1
    with active_graph(NodeGraph("ng2")) as ng2:
        assert ng1.uuid != ng2.uuid
        assert get_current_graph() == ng2
        with active_graph(NodeGraph("ng3")) as ng3:
            assert get_current_graph() == ng3
        assert get_current_graph() == ng2
