def test_link_another_node_graph(ng, ng_decorator):
    """Test link between two node_graph."""
    try:
        ng.links.new(ng.nodes["add1"].outputs[0], ng_decorator.nodes["add3"].inputs[1])
    except Exception as e:
        assert "Can not link sockets from different NodeGraph" in str(e)
