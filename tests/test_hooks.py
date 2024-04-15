
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



def test_from_dict(nt_decorator):
    """Export NodeGraph to dict."""
    nt = nt_decorator
    assert len(nt.links) == 3
    nt.nodes.post_deletion_hooks = [node_deletion_hook]
    nt.nodes.delete('add2')
    assert len(nt.links) == 1

