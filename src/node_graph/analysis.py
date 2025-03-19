from __future__ import annotations
import numpy as np
from typing import Any, Dict, List, Set, TYPE_CHECKING
from node_graph.link import NodeLink
from node_graph import Node
from node_graph.socket import NodeSocketNamespace
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import depth_first_order

if TYPE_CHECKING:
    from node_graph import NodeGraph
# or from scipy.sparse.csgraph import breadth_first_order, connected_components, etc.


def build_adjacency_matrix(graph: NodeGraph):
    """
    Build a sparse adjacency matrix where entry (i, j) == 1
    if there is a link from node i to node j.
    """
    # 1) Map each node name -> integer index
    nodes = list(graph.nodes)  # or however you get the Node list
    name_to_index = {node.name: i for i, node in enumerate(nodes)}
    n = len(nodes)

    # 2) Collect edges in "row, col" format
    row = []
    col = []
    for link in graph.links:
        if (
            link.from_node.name not in name_to_index
            or link.to_node.name not in name_to_index
        ):
            continue
        i = name_to_index[link.from_node.name]
        j = name_to_index[link.to_node.name]
        row.append(i)
        col.append(j)

    # 3) Build a coo_matrix of shape (n,n) with 1’s for edges
    data = np.ones(len(row), dtype=np.int8)
    adjacency = coo_matrix((data, (row, col)), shape=(n, n))

    return adjacency, name_to_index, nodes


class NodeGraphAnalysis:
    """
    Utility to analyze a NodeGraph, with caching to handle large graphs:
      - get_input_links / get_output_links
      - get_direct_children / get_all_descendants
      - compare_graphs by node name
    """

    def __init__(self, graph: NodeGraph):
        self.graph = graph

        # A simple integer to track if our analysis cache is up to date
        # We assume the NodeGraph increments some 'graph._version' each time
        # a node or link is added/removed, etc. If you don't have that,
        # you can implement your own triggers or approach.
        self._cached_version = -1
        self._adjacency = None
        self._name_to_idx = {}
        self._nodes_list = []
        # Caches
        self._cache_input_links: Dict[str, List[str]] = {}
        self._cache_output_links: Dict[str, List[str]] = {}
        self._cache_descendants: Dict[str, Set[str]] = {}

    # -------------------------------------------------------------------------
    # Public API that uses cached data
    # -------------------------------------------------------------------------

    def get_input_links(self, node: Node) -> List[NodeLink]:
        """
        Return all links leading INTO the given node (by name-based lookup).
        """
        self._ensure_cache_valid()
        return self._cache_input_links.get(node.name, [])

    def get_output_links(self, node: Node) -> List[NodeLink]:
        """
        Return all links leading OUT OF the given node (by name-based lookup).
        """
        self._ensure_cache_valid()
        return self._cache_output_links.get(node.name, [])

    def get_direct_children(self, node: Node) -> List[Node]:
        """
        Nodes that receive a link from `node`.
        """
        self._ensure_cache_valid()
        links = self._cache_output_links.get(node.name, [])
        # Each link's 'to_node' is the child
        return [lk for lk in links]

    def get_all_descendants(self, node: Node) -> list[str]:

        self._ensure_cache_valid()
        return self._cache_descendants.get(node.name, [])

    @staticmethod
    def compare_graphs(g1: NodeGraph, g2: NodeGraph) -> Dict[str, Any]:
        """
        Compare two NodeGraphs by NAME-based node identity. Return dict:
        {
            "added_nodes":    list of node names in g2 but not in g1
            "removed_nodes":  list of node names in g1 but not in g2
            "modified_nodes":  list of node names that appear in both but differ
        }

        "differ" = input links differ OR input socket values differ (no output check).
        """
        summary = {
            "added_nodes": [],
            "removed_nodes": [],
            "modified_nodes": [],
        }

        # Map by name
        g1_nodes_by_name = {n.name: n for n in g1.nodes}
        g2_nodes_by_name = {n.name: n for n in g2.nodes}

        set1 = set(g1_nodes_by_name.keys())
        set2 = set(g2_nodes_by_name.keys())

        # Identify added/removed
        removed = set1 - set2
        added = set2 - set1
        summary["removed_nodes"] = sorted(list(removed))
        summary["added_nodes"] = sorted(list(added))

        # For nodes present in both, check changes
        common = set1.intersection(set2)
        for nname in common:
            node1 = g1_nodes_by_name[nname]
            node2 = g2_nodes_by_name[nname]
            if NodeGraphAnalysis._node_changed(g1, node1, g2, node2):
                summary["modified_nodes"].append(nname)

        # Sort changed nodes for consistent output
        summary["modified_nodes"].sort()
        return summary

    def build_connectivity(self):
        self._ensure_cache_valid()
        connectivity = {
            "child_node": self._cache_descendants,
            "input_node": self._cache_input_links,
            "output_node": self._cache_output_links,
        }
        return connectivity

    # -------------------------------------------------------------------------
    # Internals
    # -------------------------------------------------------------------------
    @staticmethod
    def _node_changed(g1: NodeGraph, n1: Node, g2: NodeGraph, n2: Node) -> bool:
        """
        Decide if n1 and n2 differ by:
          - input links
          - input socket values
        """
        if NodeGraphAnalysis._input_links_changed(g1, n1, g2, n2):
            return True
        if NodeGraphAnalysis._input_values_changed(n1, n2):
            return True
        return False

    @staticmethod
    def _input_links_changed(g1: NodeGraph, n1: Node, g2: NodeGraph, n2: Node) -> bool:
        """Compare input links (all links where to_node == n1 vs. to_node == n2)."""
        # We'll gather a set of (from_node_name, from_socket_name) for each
        in_links_1 = set()
        for lk in g1.links:
            if lk.to_node == n1:
                in_links_1.add((lk.from_node.name, lk.from_socket._name))

        in_links_2 = set()
        for lk in g2.links:
            if lk.to_node == n2:
                in_links_2.add((lk.from_node.name, lk.from_socket._name))

        return in_links_1 != in_links_2

    @staticmethod
    def _input_values_changed(n1: Node, n2: Node) -> bool:
        """
        Compare only *input* socket values.
        We skip output sockets, as requested.
        """
        in1 = n1.get_input_names()
        in2 = n2.get_input_names()

        # If the sets of input socket names differ, we consider them changed
        if set(in1) != set(in2):
            return True

        # For matching input names, compare values
        for name in in1:
            if isinstance(n1.inputs[name], NodeSocketNamespace):
                continue
            v1 = n1.inputs[name].value
            v2 = n2.inputs[name].value
            if NodeGraphAnalysis._values_different(v1, v2):
                return True
        return False

    @staticmethod
    def _values_different(v1: Any, v2: Any) -> bool:
        """
        Safe-compare that won't fail for NumPy arrays. You can expand logic
        for other special cases. If you don't use NumPy, or if your array
        type is different, adjust accordingly.
        """
        # Case 1: Different types => different
        if type(v1) != type(v2):
            return True

        # Optionally handle None vs. non-None
        if v1 is None and v2 is None:
            return False
        if (v1 is None) ^ (v2 is None):
            return True

        # If both are NumPy arrays, compare with array_equal
        if isinstance(v1, np.ndarray) and isinstance(v2, np.ndarray):
            return not np.array_equal(v1, v2)

        # Fallback to normal "!=" comparison
        return v1 != v2

    # -------------------------------------------------------------------------
    # Caching logic
    # -------------------------------------------------------------------------
    def _ensure_cache_valid(self):
        """
        If the graph version changed, rebuild the adjacency-based caches:
          - input_links[node.name]
          - output_links[node.name]
          - all_descendants[node.name]
        """
        current_version = getattr(self.graph, "_version", 0)
        if current_version != self._cached_version:
            self._rebuild_cache()
            self._cached_version = current_version

    def _rebuild_cache(self):
        """
        Rebuild adjacency caches for all nodes:
          self._cache_input_links[name] = [links leading into name]
          self._cache_output_links[name] = [links from name]
          self._cache_descendants[name] = set of all downstream node names
        """
        self._cache_input_links.clear()
        self._cache_output_links.clear()
        self._cache_descendants.clear()

        # Initialize empty lists for each node name
        for node in self.graph.nodes:
            self._cache_input_links[node.name] = []
            self._cache_output_links[node.name] = []

        # Populate input/output links
        for link in self.graph.links:
            from_name = link.from_node.name
            to_name = link.to_node.name
            # in case the node does not belong to the graph
            if from_name not in self.graph.nodes or to_name not in self.graph.nodes:
                continue
            self._cache_output_links[from_name].append(to_name)
            self._cache_input_links[to_name].append(from_name)

        # For descendants, do a DFS/BFS from each node
        self._adjacency, self._name_to_idx, self._nodes_list = build_adjacency_matrix(
            self.graph
        )
        for node in self.graph.nodes:
            if node.name not in self._name_to_idx:
                self._cache_descendants[node.name] = []

            idx = self._name_to_idx[node.name]
            order, _ = depth_first_order(self._adjacency, idx)
            # Filter out the starting node
            order = [x for x in order if x != idx]
            self._cache_descendants[node.name] = [
                self._nodes_list[x].name for x in order
            ]
