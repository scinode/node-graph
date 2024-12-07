def node_deletion_hook(self, node):
    """Hook for node deletion.

    Args:
        node (Node): a node to be deleted.
    """
    # remove all links to the node
    link_index = []
    for index, link in enumerate(self.parent.links):
        if link.from_node.name == node.name or link.to_node.name == node.name:
            link_index.append(index)
    del self.parent.links[link_index]


def test_from_dict(ng_decorator):
    """Export NodeGraph to dict."""
    ng = ng_decorator
    assert len(ng.links) == 3
    ng.nodes.post_deletion_hooks = [node_deletion_hook]
    ng.delete_nodes("add2")
    assert len(ng.links) == 1
