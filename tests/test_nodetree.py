from node_graph import NodeGraph


def test_to_dict(nt):
    """Export NodeGraph to dict."""
    ntdata = nt.to_dict()
    assert len(ntdata["nodes"]) == 3
    assert len(ntdata["links"]) == 2


def test_from_dict(nt_decorator):
    """Export NodeGraph to dict."""
    ntdata = nt_decorator.to_dict()
    nt = NodeGraph.from_dict(ntdata)
    assert len(nt.nodes) == 4
    assert len(nt.links) == 3


def test_new_node(nt):
    """Export NodeGraph to dict."""
    nt.nodes.new("TestAdd")
    assert len(nt.nodes) == 4
