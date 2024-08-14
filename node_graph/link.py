from __future__ import annotations


class NodeLink:
    """Link connect two sockets."""

    def __init__(self, from_socket: "Socket", to_socket: "Socket") -> None:
        """init a instance of Link

        Args:
            from_socket (Socket): The socket where the link originates from.
            to_socket (Socket): The socket where the link connects to.
        """
        self.from_socket: "Socket" = from_socket
        self.from_node = from_socket.node
        self.to_socket: "Socket" = to_socket
        self.to_node = to_socket.node
        self.state: bool = False
        self.check_socket_match()
        self.mount()

    @property
    def name(self) -> str:
        return "{}.{} -> {}.{}".format(
            self.from_node.name,
            self.from_socket.name,
            self.to_node.name,
            self.to_socket.name,
        )

    def check_socket_match(self) -> None:
        """Check if the socket type match, and belong to the same node graph."""
        if self.from_node.parent != self.to_node.parent:
            raise Exception(
                "Can not link sockets from different {}. {} and {}".format(
                    self.from_node.parent.__class__.__name__,
                    self.from_node.parent,
                    self.to_node.parent,
                )
            )

        if (
            self.from_socket.identifier.upper().split(".")[-1] == "ANY"
            or self.to_socket.identifier.upper().split(".")[-1] == "ANY"
        ):
            return
        if self.from_socket.identifier.upper() != self.to_socket.identifier.upper():
            raise Exception(
                "Socket type do not match. Socket {} can not connect to socket {}".format(
                    self.from_socket.identifier, self.to_socket.identifier
                )
            )

    def mount(self) -> None:
        """Create a link trigger the update action for the sockets."""
        self.from_socket.links.append(self)
        if len(self.to_socket.links) < self.to_socket.link_limit:
            self.to_socket.links.append(self)
        else:
            # handle multi-link here
            raise Exception(
                "Socket {}: number of links {} larger than the link limit {}.".format(
                    self.to_socket.name,
                    len(self.to_socket.links) + 1,
                    self.to_socket.link_limit,
                )
            )

    def unmount(self) -> None:
        """unmount link from node"""
        i = 0
        for link in self.from_socket.links:
            if (
                link.from_node == self.from_node
                and link.from_socket == self.from_socket
                and link.to_node == self.to_node
                and link.to_socket == self.to_socket
            ):
                break
            i += 1
        del self.from_socket.links[i]
        #
        i = 0
        for link in self.to_socket.links:
            if (
                link.from_node == self.from_node
                and link.from_socket == self.from_socket
                and link.to_node == self.to_node
                and link.to_socket == self.to_socket
            ):
                break
            i += 1
        del self.to_socket.links[i]

    def to_dict(self) -> dict:
        """Data to be saved to database"""
        dbdata = {
            "from_socket": self.from_socket.name,
            "from_node": self.from_node.name,
            "from_socket_uuid": self.from_socket.uuid,
            "to_socket": self.to_socket.name,
            "to_node": self.to_node.name,
            "state": self.state,
        }
        return dbdata

    def copy(self) -> None:
        """We can not simply copy the link, because the link is related to the node."""
        pass

    def __repr__(self) -> str:
        s = ""
        s += 'NodeLink(from="{}.{}", to="{}.{}")'.format(
            self.from_node.name,
            self.from_socket.name,
            self.to_node.name,
            self.to_socket.name,
        )
        return s
