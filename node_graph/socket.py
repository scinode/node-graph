from uuid import uuid1
from node_graph.property import NodeProperty


class NodeSocket:
    """Socket object.
    Input and ouput sockets of a Node.

    Attributes:
        name (str): socket name.
        node (Node): node this socket belongs to.
        type (str): socket type.
        inner_id (int): inner_id of this socket in the SocketCollection.
        links (list): links
        property (unknown):
        link_limit (int): maxminum number of link.
    """

    # this is the class of the property object
    node_property = NodeProperty

    identifier: str = "NodeSocket"
    default_value: float = 0.0
    link_limit: int = 1

    def __init__(self, name, parent=None, type="INPUT", inner_id=0, uuid=None) -> None:
        """Init a instance of NodeSocket.

        Args:
            name (str): name of the socket
            node (_type_, optional): _description_. Defaults to None.
            inner_id (int, optional): _description_. Defaults to 0.
        """
        self.name = name
        self.parent = parent
        self.type = type
        self.inner_id = inner_id
        self.uuid = uuid or str(uuid1())
        self.links = []
        self.property = None

    @property
    def node(self):
        return self.parent

    def to_dict(self):
        """Export to a dictionary.
        Data to be saved to database. For basic JSON support.
        """
        # data from socket itself
        dbdata = {
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

    def add_link(self, link):
        """Handle multi-link here"""
        pass

    def add_property(self, identifier, name=None, **kwargs):
        """Add property to this socket."""

        if name is None:
            name = self.name

        self.property = self.node_property.new(identifier, name=name, data=kwargs)

    @classmethod
    def from_dict(cls, data):
        """Rebuild Socket object from dictionary representation."""
        socket = cls(data["name"], type=data["type"])
        return socket

    @property
    def value(self):
        return self.property.value

    @value.setter
    def value(self, value):
        self.property.value = value

    def copy(self, node=None, is_ref=False):
        """Copy this socket.

        Args:
            node (Node, optional): node that this socket bound to. Defaults to None.
            is_ref (bool, optional): the node is a reference node, thus the
                uuid of the socket will not change. Defaults to False.

        Returns:
            _type_: _description_
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
