from __future__ import annotations
from uuid import uuid1
from node_graph.property import NodeProperty
from typing import List, Optional, Dict, Any


class NodeSocket:
    """Socket object.
    Input and ouput sockets of a Node.

    Attributes:
        name (str): socket name.
        node (Node): node this socket belongs to.
        type (str): socket type.
        inner_id (int): inner_id of this socket in the SocketCollection.
        links (List[Link]): links
        property (Optional[NodeProperty]):
        link_limit (int): maximum number of links.
    """

    # this is the class of the property object
    node_property = NodeProperty

    identifier: str = "NodeSocket"
    default_value: float = 0.0

    def __init__(
        self,
        name: str,
        parent=None,
        type: str = "INPUT",
        inner_id: int = 0,
        uuid: Optional[str] = None,
        link_limit: int = 1,
    ) -> None:
        """Init a instance of NodeSocket.

        Args:
            name (str): name of the socket
            parent (Optional[Node]): parent node. Defaults to None.
            type (str, optional): socket type. Defaults to "INPUT".
            inner_id (int, optional): inner id. Defaults to 0.
            uuid (Optional[str], optional): unique identifier. Defaults to None.
            link_limit (int, optional): maximum number of links. Defaults to 1.
        """
        self.name: str = name
        self.parent: Optional["Node"] = parent
        self.type: str = type
        self.inner_id: int = inner_id
        self.uuid: str = uuid or str(uuid1())
        self.links: List["Link"] = []
        self.property: Optional[NodeProperty] = None
        self.link_limit: int = link_limit

    @property
    def node(self) -> "Node":
        return self.parent

    def to_dict(self) -> Dict[str, Any]:
        """Export to a dictionary.
        Data to be saved to database. For basic JSON support.
        """
        # data from socket itself
        dbdata: Dict[str, Any] = {
            "name": self.name,
            "identifier": self.identifier,
            "uuid": self.uuid,
            "node_uuid": self.node.uuid,
            "type": self.type,
            "link_limit": self.link_limit,
            "links": [],
            "serialize": self.get_serialize(),
            "deserialize": self.get_deserialize(),
        }
        # data from linked sockets
        for link in self.links:
            if self.type == "INPUT":
                dbdata["links"].append(
                    {
                        "from_node": link.from_node.name,
                        "from_socket": link.from_socket.name,
                        "from_socket_uuid": link.from_socket.uuid,
                    }
                )
            else:
                dbdata["links"].append(
                    {
                        "to_node": link.to_node.name,
                        "to_socket": link.to_socket.name,
                        "to_socket_uuid": link.to_socket.uuid,
                    }
                )
        return dbdata

    def add_link(self, link: "Link") -> None:
        """Handle multi-link here"""
        pass

    def add_property(
        self, identifier: str, name: Optional[str] = None, **kwargs: Any
    ) -> None:
        """Add property to this socket."""

        if name is None:
            name = self.name

        self.property = self.node_property.new(identifier, name=name, data=kwargs)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NodeSocket":
        """Rebuild Socket object from dictionary representation."""
        socket = cls(data["name"], type=data["type"])
        return socket

    @property
    def value(self) -> Any:
        return self.property.value

    @value.setter
    def value(self, value: Any) -> None:
        self.property.value = value

    def copy(self, node: Optional["Node"] = None, is_ref: bool = False) -> "NodeSocket":
        """Copy this socket.

        Args:
            node (Node, optional): node that this socket bound to. Defaults to None.
            is_ref (bool, optional): the node is a reference node, thus the
                uuid of the socket will not change. Defaults to False.

        Returns:
            NodeSocket: copied socket
        """
        node = self.node if node is None else node
        uuid = self.uuid if is_ref else None
        s = self.__class__(self.name, node, self.type, self.inner_id, uuid=uuid)
        if self.property:
            s.property = self.property.copy()
        return s

    def __repr__(self) -> str:
        s = ""
        s += '{}(name="{}", node="{}", value = {})'.format(
            self.__class__.__name__, self.name, self.node.name, self.property.value
        )
        return s
