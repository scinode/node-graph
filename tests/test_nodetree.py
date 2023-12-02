from node_graph import NodeGraph


def test_to_dict(nt):
    """Export NodeGraph to dict."""
    ntdata = nt.to_dict()
    assert len(ntdata["nodes"]) == len(nt.nodes)
    assert len(ntdata["links"]) == len(nt.links)


def test_from_dict(nt_decorator):
    """Export NodeGraph to dict."""
    nt = nt_decorator
    ntdata = nt_decorator.to_dict()
    nt1 = NodeGraph.from_dict(ntdata)
    assert len(nt.nodes) == len(nt1.nodes)
    assert len(nt.links) == len(nt1.links)


def test_new_node(nt):
    """Export NodeGraph to dict."""
    n = len(nt.nodes)
    nt.nodes.new("TestAdd")
    assert len(nt.nodes) == n + 1
