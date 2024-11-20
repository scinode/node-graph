def test_base_type():
    """Test base type property."""
    from node_graph.property import NodeProperty

    p = NodeProperty.new("node_graph.int")
    assert "serialize" in p.to_dict()
