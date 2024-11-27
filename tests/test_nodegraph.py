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
    """Test new node."""
    n = len(ng.nodes)
    ng.nodes.new("node_graph.test_add")
    assert len(ng.nodes) == n + 1


def test_delete_node(ng):
    """Test delete node."""
    n = len(ng.nodes)
    nlink = len(ng.links)
    ng.nodes.new("node_graph.test_add", name="add3")
    ng.links.new(ng.nodes["add1"].outputs[0], ng.nodes["add3"].inputs["y"])
    assert len(ng.nodes) == n + 1
    assert len(ng.links) == nlink + 1
    ng.delete_nodes(["add3"])
    assert len(ng.nodes) == n
    assert len(ng.links) == nlink


def test_copy(ng):
    """Test copy node graph"""
    n = len(ng.nodes)
    nlink = len(ng.links)
    ng1 = ng.copy()
    assert len(ng1.nodes) == n
    assert len(ng1.links) == nlink


def test_add(ng):
    """Test add another nodegraph."""
    n = len(ng.nodes)
    nlink = len(ng.links)
    ng1 = NodeGraph(name="test_node_group")
    ng1.nodes.new("node_graph.test_float", "float3", value=4.0, t=3)
    ng1.nodes.new("node_graph.test_float", "float4", value=3.0)
    ng += ng1
    assert len(ng.nodes) == n + 2
    assert len(ng.links) == nlink
