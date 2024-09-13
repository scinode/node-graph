from node_graph import NodeGraph


def test_from_dict(ng_decorator):
    """Export NodeGraph to dict."""
    ng = ng_decorator
    ntdata = ng_decorator.to_dict()
    ng1 = NodeGraph.from_dict(ntdata)
    assert len(ng.nodes) == len(ng1.nodes)
    assert len(ng.links) == len(ng1.links)
    assert ng.to_dict() == ng1.to_dict()


def test_new_node(ng):
    """Export NodeGraph to dict."""
    n = len(ng.nodes)
    ng.nodes.new("node_graph.test_add")
    assert len(ng.nodes) == n + 1
