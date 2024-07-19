def test_link_another_node_graph(nt, nt_decorator):
    """Test link between two node_graph."""
    try:
        nt.links.new(nt.nodes["add1"].outputs[0], nt_decorator.nodes["add3"].inputs[1])
    except Exception as e:
        assert "Can not link sockets from different NodeGraph" in str(e)
