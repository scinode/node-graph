from __future__ import annotations


class NodeLink:
    """Link connect two sockets."""

    def __init__(self, from_socket: "Socket", to_socket: "Socket") -> None:
        """init a instance of Link

        Args:
            from_socket (Socket): The socket where the link originates from.
            to_socket (Socket): The socket where the link connects to.
        """
        self.from_socket = from_socket
        self.from_node = from_socket._node
        self.to_socket = to_socket
        self.to_node = to_socket._node
        self.check_socket_match()
        self.mount()

    @property
    def name(self) -> str:
        return "{}.{} -> {}.{}".format(
            self.from_node.name,
            self.from_socket._scoped_name,
            self.to_node.name,
            self.to_socket._scoped_name,
        )

    def check_socket_match(self) -> None:
        """Check if the socket type match, and belong to the same node graph."""
        if self.from_node.graph != self.to_node.graph:
            raise Exception(
                "Can not link sockets from different {}. {} and {}".format(
                    self.from_node.graph.__class__.__name__,
                    self.from_node.graph,
                    self.to_node.graph,
                )
            )

        if (
            self.from_socket._identifier.lower().split(".")[-1] == "any"
            or self.to_socket._identifier.lower().split(".")[-1] == "any"
        ):
            return
        if self.from_socket._identifier.lower() != self.to_socket._identifier.lower():
            raise Exception(
                "Socket type do not match. Socket {} can not connect to socket {}".format(
                    self.from_socket._identifier,
                    self.to_socket._identifier,
                )
            )

    def mount(self) -> None:
        """Create a link trigger the update action for the sockets."""
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
        """unmount link from node"""
        i = 0
        for link in self.from_socket._links:
            if (
                link.from_node.name == self.from_node.name
                and link.from_socket._name == self.from_socket._name
                and link.to_node.name == self.to_node.name
                and link.to_socket._name == self.to_socket._name
            ):
                break
            i += 1
        del self.from_socket._links[i]
        #
        i = 0
        for link in self.to_socket._links:
            if (
                link.from_node.name == self.from_node.name
                and link.from_socket._name == self.from_socket._name
                and link.to_node.name == self.to_node.name
                and link.to_socket._name == self.to_socket._name
            ):
                break
            i += 1
        del self.to_socket._links[i]

    def to_dict(self) -> dict:
        """Data to be saved to database"""
        dbdata = {
            "from_socket": self.from_socket._scoped_name,
            "from_node": self.from_node.name,
            "to_socket": self.to_socket._scoped_name,
            "to_node": self.to_node.name,
        }
        return dbdata

    def copy(self) -> None:
        """We can not simply copy the link, because the link is related to the node."""
        pass

    def __repr__(self) -> str:
        s = ""
        s += 'NodeLink(from="{}.{}", to="{}.{}")'.format(
            self.from_node.name,
            self.from_socket._scoped_name,
            self.to_node.name,
            self.to_socket._scoped_name,
        )
        return s
