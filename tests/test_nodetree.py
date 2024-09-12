from node_graph import NodeGraph


def test_from_dict(nt_decorator):
    """Export NodeGraph to dict."""
    nt = nt_decorator
    ntdata = nt_decorator.to_dict()
    nt1 = NodeGraph.from_dict(ntdata)
    assert len(nt.nodes) == len(nt1.nodes)
    assert len(nt.links) == len(nt1.links)
    assert nt.to_dict() == nt1.to_dict()


def test_new_node(nt):
    """Export NodeGraph to dict."""
    n = len(nt.nodes)
    nt.nodes.new("node_graph.test_add")
    assert len(nt.nodes) == n + 1
