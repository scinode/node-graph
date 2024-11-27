from __future__ import annotations
from uuid import uuid1
from node_graph.property import NodeProperty
from typing import List, Optional, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from node_graph.node import Node
    from node_graph.link import NodeLink


class NodeSocket:
    """Socket object for input and output sockets of a Node.

    Attributes:
        name (str): Socket name.
        node (Node): Node this socket belongs to.
        type (str): Socket type, either "INPUT" or "OUTPUT".
        list_index (int): Index of this socket in the SocketCollection.
        links (List[Link]): Connected links.
        property (Optional[NodeProperty]): Associated property.
        link_limit (int): Maximum number of links.
    """

    # Class reference to the NodeProperty class
    node_property = NodeProperty

    identifier: str = "NodeSocket"
    property_identifier: Optional[str] = None
    default_value: Any = None

    def __init__(
        self,
        name: str,
        parent: Optional["Node"] = None,
        socket_type: str = "INPUT",
        list_index: int = 0,
        uuid: Optional[str] = None,
        link_limit: int = 1,
        property_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Initialize an instance of NodeSocket.

        Args:
            name (str): Name of the socket.
            parent (Optional[Node]): Parent node. Defaults to None.
            type (str, optional): Socket type. Defaults to "INPUT".
            list_index (int, optional): Inner index. Defaults to 0.
            uuid (Optional[str], optional): Unique identifier. Defaults to None.
            link_limit (int, optional): Maximum number of links. Defaults to 1.
        """
        self.name: str = name
        self.parent: Optional["Node"] = parent
        self.socket_type: str = socket_type
        self.list_index: int = list_index
        self.uuid: str = uuid or str(uuid1())
        self.links: List["NodeLink"] = []
        self.property: Optional[NodeProperty] = None
        self.link_limit: int = link_limit
        # Conditionally add a property if property_identifier is provided
        if self.property_identifier:
            self.add_property(self.property_identifier, name, **(property_data or {}))

    @property
    def node(self) -> "Node":
        return self.parent

    def to_dict(self) -> Dict[str, Any]:
        """Export the socket to a dictionary for database storage."""
        dbdata: Dict[str, Any] = {
            "name": self.name,
            "identifier": self.identifier,
            "node_uuid": self.node.uuid if self.node else None,
            "type": self.socket_type,
            "link_limit": self.link_limit,
            "links": [],
            "list_index": self.list_index,
        }
        for link in self.links:
            if self.socket_type == "INPUT":
                dbdata["links"].append(
                    {
                        "from_node": link.from_node.name,
                        "from_socket": link.from_socket.name,
                    }
                )
            else:
                dbdata["links"].append(
                    {
                        "to_node": link.to_node.name,
                        "to_socket": link.to_socket.name,
                    }
                )
        # data from property
        if self.property is not None:
            dbdata["property"] = self.property.to_dict()
        else:
            dbdata["property"] = None
        # Conditionally add serializer/deserializer if they are defined
        if hasattr(self, "get_serialize") and callable(self.get_serialize):
            dbdata["serialize"] = self.get_serialize()

        if hasattr(self, "get_deserialize") and callable(self.get_deserialize):
            dbdata["deserialize"] = self.get_deserialize()
        return dbdata

    def add_link(self, link: "NodeLink") -> None:
        """Add a link to this socket."""
        if len(self.links) < self.link_limit or self.link_limit == 0:
            self.links.append(link)
        else:
            raise ValueError(
                f"Link limit of {self.link_limit} reached for socket '{self.name}'."
            )

    def add_property(
        self, identifier: str, name: Optional[str] = None, **kwargs: Any
    ) -> None:
        """Add a property to this socket."""
        if name is None:
            name = self.name
        self.property = self.node_property.new(identifier, name=name, data=kwargs)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NodeSocket":
        """Rebuild a NodeSocket object from a dictionary."""
        socket = cls(data["name"], socket_type=data["type"])
        return socket

    @property
    def value(self) -> Any:
        if self.property:
            return self.property.value
        return None

    @value.setter
    def value(self, value: Any) -> None:
        if self.property:
            self.property.value = value
        else:
            raise AttributeError(
                f"Socket '{self.name}' has no property to set a value."
            )

    def copy(self, node: Optional["Node"] = None, is_ref: bool = False) -> "NodeSocket":
        """Copy this socket.

        Args:
            node (Node, optional): Node that this socket will belong to. Defaults to None.
            is_ref (bool, optional): If True, the UUID of the socket will not change. Defaults to False.

        Returns:
            NodeSocket: The copied socket.
        """
        node = self.node if node is None else node
        uuid = self.uuid if is_ref else None
        socket_copy = self.__class__(
            self.name,
            parent=node,
            socket_type=self.socket_type,
            list_index=self.list_index,
            uuid=uuid,
            link_limit=self.link_limit,
        )
        if self.property:
            socket_copy.property = self.property.copy()
        return socket_copy

    def __repr__(self) -> str:
        value = self.property.value if self.property else None
        return f"{self.__class__.__name__}(name='{self.name}', node='{self.node.name if self.node else None}', value={value})"
