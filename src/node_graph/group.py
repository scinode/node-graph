class Group:
    """
    A group that can be used to create dependencies between multiple nodes/sockets.
    """

    def __init__(self, *items):
        self.items = list(items)

    def __rshift__(self, other):
        for item in self.items:
            item >> other
        return other

    def __lshift__(self, other):
        for item in self.items:
            item << other
        return other


def group(*items):
    """Create a group of items (nodes/sockets)."""
    return Group(*items)
