from node_graph import NodeGraph, node


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
    ng.add_node("node_graph.test_add")
    assert len(ng.nodes) == n + 1


def test_delete_node(ng):
    """Test delete node."""
    n = len(ng.nodes)
    nlink = len(ng.links)
    ng.add_node("node_graph.test_add", name="add3")
    ng.add_link(ng.nodes["add1"].outputs[0], ng.nodes["add3"].inputs["y"])
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
    ng1.add_node("node_graph.test_float", "float3", value=4.0, t=3)
    ng1.add_node("node_graph.test_float", "float4", value=3.0)
    ng = ng + ng1
    assert len(ng.nodes) == n + 2
    assert len(ng.links) == nlink


def test_copy_subset(ng):
    """Test copy subset of nodes."""
    ng1 = ng.copy_subset(["add1", "add2"])
    assert len(ng1.nodes) == 3
    assert len(ng1.links) == 2
    assert "float1" in ng1.get_node_names()


def test_get_items(ng):
    """Test get items."""
    ng1 = ng[["add1", "add2"]]
    assert len(ng1.nodes) == 3
    assert len(ng1.links) == 2
    assert "float1" in ng1.get_node_names()


def test_load_graph():
    @node(
        outputs=[{"name": "sum"}, {"name": "product"}],
    )
    def test(a, b=1, **kwargs):
        return {"sum": a + b, "product": a * b}

    ng = NodeGraph()
    test1 = ng.add_node(test, "test1")
    test1.set(
        {
            "a": 1,
            "b": 2,
            "kwargs": {"c": 1, "d": 2},
        }
    )
    ngdata = ng.to_dict()
    # load graph
    ng1 = NodeGraph.from_dict(ngdata)
    ng1.nodes.test1.inputs.kwargs._value = {"c": 1, "d": 2}
