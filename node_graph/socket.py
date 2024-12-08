from __future__ import annotations
from uuid import uuid1
from node_graph.property import NodeProperty
from typing import List, Optional, Dict, Any, TYPE_CHECKING, Callable, Union
from node_graph.collection import Collection, decorator_check_identifier_name
from node_graph.utils import get_item_class


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
        arg_type: Optional[str] = "kwargs",
        metadata: Optional[dict] = None,
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
        self.arg_type: Optional[str] = arg_type
        self.metadata: Optional[dict] = metadata or {}
        # Conditionally add a property if property_identifier is provided
        if self.property_identifier:
            property_data = property_data or {}
            property_data.pop("identifier", None)
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
            "arg_type": self.arg_type,
            "metadata": self.metadata,
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

    def copy(self, parent: Optional["Node"] = None) -> "NodeSocket":
        """Copy this socket.

        Args:
            parent (Node, optional): Node that this socket will belong to. Defaults to None.

        Returns:
            NodeSocket: The copied socket.
        """
        parent = self.parent if parent is None else parent
        socket_copy = self.__class__(
            self.name,
            parent=parent,
            socket_type=self.socket_type,
            list_index=self.list_index,
            link_limit=self.link_limit,
        )
        if self.property:
            socket_copy.property = self.property.copy()
        return socket_copy

    def __repr__(self) -> str:
        value = self.property.value if self.property else None
        return f"{self.__class__.__name__}(name='{self.name}', value={value})"


class NodeSocketNamespace(NodeSocket, Collection):
    """A NodeSocket that also acts as a namespace (collection) of other sockets."""

    identifier: str = "node_graph.namespace"

    def __init__(
        self,
        name: str,
        parent: Optional["Node"] = None,
        socket_type: str = "INPUT",
        list_index: int = 0,
        uuid: Optional[str] = None,
        link_limit: int = 1,
        arg_type: Optional[str] = "kwargs",
        metadata: Optional[dict] = None,
        property_data: Optional[Dict[str, Any]] = None,
        pool: Optional[object] = None,
        entry_point: Optional[str] = "node_graph.socket",
        post_creation_hooks: Optional[List[Callable]] = None,
        post_deletion_hooks: Optional[List[Callable]] = None,
    ) -> None:
        # Initialize NodeSocket first
        NodeSocket.__init__(
            self,
            name=name,
            parent=parent,
            socket_type=socket_type,
            list_index=list_index,
            uuid=uuid,
            link_limit=link_limit,
            arg_type=arg_type,
            metadata=metadata,
            property_data=property_data,
        )
        # Then initialize Collection
        Collection.__init__(
            self,
            parent=parent,
            pool=pool,
            entry_point=entry_point,
            post_creation_hooks=post_creation_hooks,
            post_deletion_hooks=post_deletion_hooks,
        )

    @decorator_check_identifier_name
    def _new(
        self,
        identifier: Union[str, type],
        name: Optional[str] = None,
        link_limit: int = 1,
        arg_type: str = "kwargs",
        metadata: Optional[dict] = None,
        property_data: Optional[dict] = None,
    ) -> object:
        from node_graph.socket import NodeSocket

        socket_names = name.split(".", 1)
        if len(socket_names) > 1:
            namespace = socket_names[0]
            if namespace not in self:
                raise ValueError(
                    f"Namespace {namespace} does not exist in the socket collection."
                )
            return self[namespace]._new(
                identifier,
                socket_names[1],
                link_limit,
                arg_type,
                metadata,
                property_data,
            )
        else:
            ItemClass = get_item_class(identifier, self.pool, NodeSocket)
            list_index = self._get_list_index()
            item = ItemClass(
                name,
                socket_type="INPUT",
                list_index=list_index,
                link_limit=link_limit,
                arg_type=arg_type,
                metadata=metadata,
                property_data=property_data,
            )
            self._append(item)
        return item

    def to_dict(self) -> Dict[str, Any]:
        data = super(NodeSocketNamespace, self).to_dict()  # Get base NodeSocket dict
        # Add nested sockets information
        data["sockets"] = [item.to_dict() for item in self._items]
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NodeSocketNamespace":
        # Create a base NodeSocket from dict first
        base_socket = NodeSocket.from_dict(data)
        # Transform into NodeSocketNamespace
        ns = cls(
            name=base_socket.name,
            parent=base_socket.parent,
            socket_type=base_socket.socket_type,
            list_index=base_socket.list_index,
            uuid=base_socket.uuid,
            link_limit=base_socket.link_limit,
            arg_type=base_socket.arg_type,
            metadata=base_socket.metadata,
            property_data=base_socket.property.to_dict()
            if base_socket.property
            else None,
        )
        # Load nested sockets
        for s_data in data.get("sockets", []):
            s = NodeSocket.from_dict(s_data)
            ns._append(s)
        return ns

    def _copy(self, parent: Optional["parent"] = None) -> "parentSocketNamespace":
        # Copy as parentSocket
        parent = self.parent if parent is None else parent
        ns_copy = self.__class__(
            self.name,
            parent=parent,
            socket_type=self.socket_type,
            list_index=self.list_index,
            link_limit=self.link_limit,
            arg_type=self.arg_type,
            metadata=self.metadata,
            property_data=self.property.to_dict() if self.property else None,
        )
        # Copy nested sockets
        for item in self._items:
            ns_copy._append(item.copy(parent=parent))
        return ns_copy

    def __repr__(self) -> str:
        nested = [item.name for item in self._items]
        return f"{self.__class__.__name__}(name='{self.name}', " f"sockets={nested})"
