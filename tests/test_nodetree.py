import time
import numpy as np
from node_graph import NodeGraph


def test_to_dict(nt):
    """Export NodeGraph to dict."""
    nt.to_dict()


def test_new_ndoe(nt):
    """Export NodeGraph to dict."""
    nt.nodes.new("TestAdd")
