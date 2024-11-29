def test_base_collection():
    """Test base collection."""
    from node_graph.collection import Collection
    from node_graph.node import Node
    from node_graph import NodeGraph

    ng = NodeGraph(name="test_base_collection")
    coll = Collection(parent=ng)
    coll.path = "builtins"
    node1 = Node(name="node1")
    node2 = Node(name="node2")
    # apend
    coll.append(node1)
    coll.append(node2)
    assert len(coll) == 2
    assert node1.parent == ng
    # copy
    coll1 = coll.copy()
    assert len(coll1) == 2
    # delete
    coll.delete(node1.name)
    assert len(coll) == 1
    # get
    assert coll.get("node2") == node2
    # get by uuid
    assert coll.get_by_uuid(node2.uuid) == node2
    # __repr__
    assert repr(coll) == "Collection()\n"
