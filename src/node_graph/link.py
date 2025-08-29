from __future__ import annotations
from typing import Dict


class NodeLink:
    """Link connecting two sockets."""

    def __init__(self, from_socket: "Socket", to_socket: "Socket") -> None:
        from node_graph import NodeGraph

        self.from_socket = from_socket
        self.to_socket = to_socket
        self.from_node = from_socket._node

        self.to_node = to_socket._node
        self.from_graph = (
            self.from_node
            if isinstance(self.from_node, NodeGraph)
            else self.from_node.graph
        )
        self.to_graph = (
            self.to_node if isinstance(self.to_node, NodeGraph) else self.to_node.graph
        )

        self.check_socket_match()
        self.mount()

    @property
    def from_label(self) -> str:
        from node_graph import NodeGraph

        if isinstance(self.from_node, NodeGraph):
            return f"_{self.from_socket._full_name.split('.')[0]}"
        return self.from_node.name

    @property
    def to_label(self) -> str:
        from node_graph import NodeGraph

        if isinstance(self.to_node, NodeGraph):
            return f"_{self.to_socket._full_name.split('.')[0]}"
        return self.to_node.name

    @property
    def name(self) -> str:
        return f"{self.from_label}.{self.from_socket._scoped_name} -> {self.to_label}.{self.to_socket._scoped_name}"

    def check_socket_match(self) -> None:
        """Check if the socket type match, and belong to the same node graph."""
        if self.from_graph is not self.to_graph:
            raise Exception(
                "Can not link sockets from different graphs. {} and {}".format(
                    self.from_graph, self.to_graph
                )
            )

        fid: str = (self.from_socket._identifier or "").lower()
        tid: str = (self.to_socket._identifier or "").lower()
        if fid.split(".")[-1] == "any" or tid.split(".")[-1] == "any":
            return
        if fid != tid:
            raise Exception(
                f"Socket type do not match. Socket {self.from_socket._identifier} can not connect "
                "to socket {self.to_socket._identifier}"
            )

    def mount(self) -> None:
        self.from_socket._links.append(self)
        if len(self.to_socket._links) < self.to_socket._link_limit:
            self.to_socket._links.append(self)
        else:
            # handle multi-link here
            raise Exception(
                "Socket {}: number of links {} larger than the link limit {}.".format(
                    self.to_socket._name,
                    len(self.to_socket._links) + 1,
                    self.to_socket._link_limit,
                )
            )

    def unmount(self) -> None:
        i = 0
        for link in self.from_socket._links:
            if (
                link.from_node is self.from_node
                and link.from_socket._name == self.from_socket._name
                and link.to_node is self.to_node
                and link.to_socket._name == self.to_socket._name
            ):
                break
            i += 1
        del self.from_socket._links[i]

        i = 0
        for link in self.to_socket._links:
            if (
                link.from_node is self.from_node
                and link.from_socket._name == self.from_socket._name
                and link.to_node is self.to_node
                and link.to_socket._name == self.to_socket._name
            ):
                break
            i += 1
        del self.to_socket._links[i]

    def to_dict(self) -> Dict[str, str]:
        return {
            "from_socket": self.from_socket._scoped_name,
            "from_node": self.from_label,
            "to_socket": self.to_socket._scoped_name,
            "to_node": self.to_label,
        }

    def copy(self) -> None:
        """We can not simply copy the link, because the link is related to the node."""
        pass

    def __repr__(self) -> str:
        return (
            f'NodeLink(from="{self.from_label}.{self.from_socket._scoped_name}", '
            + 'to="{self.to_label}.{self.to_socket._scoped_name}")'
        )
