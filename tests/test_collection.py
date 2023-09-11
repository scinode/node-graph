def test_base_collection():
    """Test base collection."""
    from node_graph.collection import Collection
    from node_graph.node import Node
    from node_graph import NodeGraph

    nt = NodeGraph(name="test_base_collection")
    coll = Collection(parent=nt)
    coll.path = "builtins"
    node1 = Node(name="node1")
    node2 = Node(name="node2")
    # apend
    coll.append(node1)
    coll.append(node2)
    assert len(coll) == 2
    assert node1.parent == nt
    # copy
    coll1 = coll.copy()
    assert len(coll1) == 2
    # delete
    coll.delete(node1.name)
    assert len(coll) == 1
