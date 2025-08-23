"""
Simple global variable approach.
Note pitfalls:
    - lack of concurrency control
    - collisions in library code
    - difficulty testing in isolation
    - etc.
"""
from contextlib import contextmanager
from contextvars import ContextVar


class CurrentGraphManager:
    _instance = None

    def __new__(cls, *args, **kwargs):
        """
        Enforce the singleton pattern. Only one instance of
        CurrentGraphManager is created for the entire process.
        """
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._graph = None  # Storage for the active graph
        return cls._instance

    def peek_current_graph(self):
        """Return the active graph or None (do NOT auto-create)."""
        return self._graph

    def get_current_graph(self):
        """
        Retrieve the current graph, or create a new one if none is set.
        """
        from node_graph.node_graph import NodeGraph

        if self._graph is None:
            self._graph = NodeGraph()
        return self._graph

    def set_current_graph(self, graph):
        """
        Set the active graph to the given instance.
        """
        self._graph = graph

    @contextmanager
    def active_graph(self, graph):
        """
        Context manager that temporarily overrides the current graph
        with `graph`, restoring the old graph when exiting the context.
        """
        old_graph = self._graph
        self._graph = graph
        try:
            yield graph
        finally:
            self._graph = old_graph


# Create a global manager instance
_manager = CurrentGraphManager()
_current_graph: ContextVar["NodeGraph | None"] = ContextVar(
    "current_graph", default=None
)


def peek_current_graph():
    return _current_graph.get()


def get_current_graph():
    from node_graph.node_graph import NodeGraph

    g = _current_graph.get()
    if g is None:
        g = NodeGraph()  # fallback to a default core graph
        _current_graph.set(g)
    return g


def set_current_graph(graph):
    _current_graph.set(graph)


@contextmanager
def active_graph(graph):
    token = _current_graph.set(graph)
    try:
        yield graph
    finally:
        _current_graph.reset(token)
