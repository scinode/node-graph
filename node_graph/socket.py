from __future__ import annotations

from node_graph.property import NodeProperty
from typing import List, Optional, Dict, Any, TYPE_CHECKING, Callable, Union
from node_graph.utils import get_item_class
from node_graph.utils import get_entries


if TYPE_CHECKING:
    from node_graph.node import Node
    from node_graph.link import NodeLink


class BaseSocket:
    """Socket object for input and output sockets of a Node.

    Attributes:
        name (str): Socket name.
        node (Node): Node this socket belongs to.
        type (str): Socket type, either "INPUT" or "OUTPUT".
        links (List[Link]): Connected links.
        property (Optional[NodeProperty]): Associated property.
        link_limit (int): Maximum number of links.
    """

    _socket_identifier: str = "BaseSocket"

    def __init__(
        self,
        name: str,
        node: Optional["Node"] = None,
        parent: Optional["NodeSocketNamespace"] = None,
        link_limit: int = 1,
        metadata: Optional[dict] = None,
    ) -> None:
        """Initialize an instance of NodeSocket.

        Args:
            name (str): Name of the socket.
            parent (Optional[Node]): Parent node. Defaults to None.
            type (str, optional): Socket type. Defaults to "INPUT".
            link_limit (int, optional): Maximum number of links. Defaults to 1.
        """
        self.socket_name: str = name
        self.socket_node: Optional["Node"] = node
        self.socket_parent: Optional["NodeSocketNamespace"] = parent
        self.socket_links: List["NodeLink"] = []
        self.socket_link_limit: int = link_limit
        self.socket_metadata: Optional[dict] = metadata or {}

    def _to_dict(self) -> Dict[str, Any]:
        """Export the socket to a dictionary for database storage."""
        data: Dict[str, Any] = {
            "name": self.socket_name,
            "identifier": self._socket_identifier,
            "link_limit": self.socket_link_limit,
            "links": [],
            "metadata": self.socket_metadata,
        }
        for link in self.socket_links:
            if self.socket_metadata.get("socket_type", "INPUT").upper() == "INPUT":
                data["links"].append(
                    {
                        "from_node": link.from_node.name,
                        "from_socket": link.from_socket.socket_name,
                    }
                )
            else:
                data["links"].append(
                    {
                        "to_node": link.to_node.name,
                        "to_socket": link.to_socket.socket_name,
                    }
                )

        # Conditionally add serializer/deserializer if they are defined
        if hasattr(self, "get_serialize") and callable(self.get_serialize):
            data["serialize"] = self.get_serialize()

        if hasattr(self, "get_deserialize") and callable(self.get_deserialize):
            data["deserialize"] = self.get_deserialize()
        return data

    @classmethod
    def _from_dict(cls, data: Dict[str, Any]) -> "NodeSocket":
        """Rebuild a NodeSocket object from a dictionary."""
        socket = cls(
            data["name"], link_limit=data["link_limit"], metadata=data["metadata"]
        )
        return socket


class NodeSocket(BaseSocket):

    _socket_identifier: str = "NodeSocket"

    _socket_property_class = NodeProperty

    _socket_property_identifier: Optional[str] = None

    def __init__(
        self,
        name: str,
        node: Optional["Node"] = None,
        parent: Optional["NodeSocketNamespace"] = None,
        link_limit: int = 1,
        metadata: Optional[dict] = None,
        property_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Initialize an instance of NodeSocket.

        Args:
            name (str): Name of the socket.
            parent (Optional[Node]): Parent node. Defaults to None.
            type (str, optional): Socket type. Defaults to "INPUT".
            link_limit (int, optional): Maximum number of links. Defaults to 1.
        """
        BaseSocket.__init__(
            self,
            name=name,
            node=node,
            parent=parent,
            link_limit=link_limit,
            metadata=metadata,
        )
        # Conditionally add a property if property_identifier is provided
        self.socket_property: Optional[NodeProperty] = None
        if self._socket_property_identifier:
            property_data = property_data or {}
            property_data.pop("identifier", None)
            self.add_property(
                self._socket_property_identifier, name, **(property_data or {})
            )

    def add_property(
        self, identifier: str, name: Optional[str] = None, **kwargs: Any
    ) -> None:
        """Add a property to this socket."""
        if name is None:
            name = self.socket_name
        self.socket_property = self._socket_property_class.new(
            identifier, name=name, data=kwargs
        )

    @property
    def socket_value(self) -> Any:
        if self.socket_property:
            return self.socket_property.value
        return None

    @socket_value.setter
    def socket_value(self, value: Any) -> None:
        self._set_socket_value(value)

    def _set_socket_value(self, value: Any) -> None:
        if isinstance(value, NodeSocket):
            self.socket_node.parent.add_link(value, self)
        elif self.socket_property:
            self.socket_property.value = value
        else:
            raise AttributeError(
                f"Socket '{self.socket_name}' has no property to set a value."
            )

    def _to_dict(self):
        data = super()._to_dict()
        # data from property
        if self.socket_property is not None:
            data["property"] = self.socket_property.to_dict()
        else:
            data["property"] = None
        return data

    def _copy(
        self, node: Optional["Node"] = None, parent: Optional["Node"] = None
    ) -> "NodeSocket":
        """Copy this socket.

        Args:
            parent (Node, optional): Node that this socket will belong to. Defaults to None.

        Returns:
            NodeSocket: The copied socket.
        """
        node = self.socket_node if node is None else node
        parent = self.socket_parent if parent is None else parent
        socket_copy = self.__class__(
            name=self.socket_name,
            node=node,
            parent=parent,
            link_limit=self.socket_link_limit,
        )
        if self.socket_property:
            socket_copy.socket_property = self.socket_property.copy()
        return socket_copy

    def __repr__(self) -> str:
        value = self.socket_property.value if self.socket_property else None
        return f"{self.__class__.__name__}(name='{self.socket_name}', value={value})"


def decorator_check_identifier_name(func: Callable) -> Callable:
    """Check identifier and name exist or not.

    Args:
        func (_type_): _description_
    """

    def wrapper_func(*args, **kwargs):
        import difflib

        identifier = args[1]
        if (
            isinstance(identifier, str)
            and identifier.upper() not in args[0]._socket_pool
        ):
            items = difflib.get_close_matches(identifier.upper(), args[0]._socket_pool)
            if len(items) == 0:
                msg = f"Identifier: {identifier} is not defined."
            else:
                msg = f"Identifier: {identifier} is not defined. Did you mean {', '.join(item.lower() for item in items)}?"
            raise ValueError(msg)
        if len(args) > 2 and args[2] in args[0]._keys():
            raise ValueError(f"{args[2]} already exists, please choose another name.")
        if kwargs.get("name", None) in args[0]._keys():
            raise ValueError(
                f"{kwargs.get('name')} already exists, please choose another name."
            )
        item = func(*args, **kwargs)
        return item

    return wrapper_func


class NodeSocketNamespace(BaseSocket):
    """A NodeSocket that also acts as a namespace (collection) of other sockets."""

    _socket_identifier: str = "node_graph.namespace"
    _RESERVED_NAMES = {
        "_socket_property_class",
        "_socket_identifier",
        "_socket_property_identifier",
        "RESERVED_NAMES",
        "socket_name",
        "socket_node",
        "socket_parent",
        "socket_links",
        "socket_property",
        "socket_link_limit",
        "_metadata",
    }

    def __init__(
        self,
        name: str,
        node: Optional["Node"] = None,
        parent: Optional["NodeSocket"] = None,
        link_limit: int = 1e6,
        metadata: Optional[dict] = None,
        pool: Optional[object] = None,
        entry_point: Optional[str] = "node_graph.socket",
    ) -> None:
        # Initialize NodeSocket first
        BaseSocket.__init__(
            self,
            name=name,
            node=node,
            parent=parent,
            link_limit=link_limit,
            metadata=metadata,
        )
        self._items: List[object] = []
        self.socket_parent = parent
        # one can specify the pool or entry_point to get the pool
        # if pool is not None, entry_point will be ignored, e.g., Link has no pool
        if pool is not None:
            self._socket_pool = pool
        elif entry_point is not None:
            self._socket_pool = get_entries(entry_point_name=entry_point)
        self.socket_is_dynamic = self.socket_metadata.get("dynamic", False)

    @decorator_check_identifier_name
    def _new(
        self,
        identifier: Union[str, type] = "node_graph.any",
        name: Optional[str] = None,
        link_limit: int = 1,
        metadata: Optional[dict] = None,
        **kwargs: Any,
    ) -> object:

        socket_names = name.split(".", 1)
        if len(socket_names) > 1:
            namespace = socket_names[0]
            if namespace not in self:
                # if the namespace is dynamic, create sub-sockets if it does not exist
                if self.socket_is_dynamic:
                    # the sub-socket should also be dynamic
                    self._new(
                        "node_graph.namespace",
                        namespace,
                        metadata={"dynamic": True},
                    )
                else:
                    raise ValueError(
                        f"Namespace {namespace} does not exist in the socket collection."
                    )
            return self[namespace]._new(
                identifier,
                socket_names[1],
                metadata=metadata,
            )
        else:
            ItemClass = get_item_class(identifier, self._socket_pool, BaseSocket)
            item = ItemClass(
                name,
                node=self.socket_node,
                parent=self.socket_parent,
                link_limit=link_limit,
                metadata=metadata,
                **kwargs,
            )
            self._append(item)
            return item

    @property
    def socket_value(self) -> Dict[str, Any]:
        return {
            item.socket_name: item.socket_value
            for item in self._items
            if item.socket_value is not None
        }

    @socket_value.setter
    def socket_value(self, value: Dict[str, Any]) -> None:
        self._set_socket_value(value)

    def _set_socket_value(self, value: Dict[str, Any] | NodeSocket) -> None:
        if isinstance(value, NodeSocket):
            self.socket_node.parent.add_link(value, self)
        elif isinstance(value, dict):
            for key, val in value.items():
                if key not in self:
                    if self.socket_is_dynamic:
                        self._new("node_graph.any", key)
                    else:
                        raise ValueError(
                            f"Socket {key} does not exist in the socket collection."
                        )
                self[key]._set_socket_value(val)
        else:
            raise ValueError(
                f"Invalid value type for socket value: {value}, expected dict or Socket."
            )

    def _to_dict(self) -> Dict[str, Any]:
        data = super(NodeSocketNamespace, self)._to_dict()  # Get base NodeSocket dict
        # Add nested sockets information
        data["value"] = self.socket_value
        return data

    @classmethod
    def _from_dict(cls, data: Dict[str, Any]) -> "NodeSocketNamespace":
        # Create a base NodeSocket from dict first
        base_socket = NodeSocket.from_dict(data)
        # Transform into NodeSocketNamespace
        ns = cls(
            name=base_socket.name,
            parent=base_socket.parent,
            link_limit=base_socket.link_limit,
            metadata=base_socket.socket_metadata,
            property_data=base_socket.socket_property.to_dict()
            if base_socket.property
            else None,
        )
        # Load nested sockets
        for s_data in data.get("sockets", []):
            s = NodeSocket.from_dict(s_data)
            ns._append(s)
        return ns

    def _copy(self, parent: Optional["NodeSocket"] = None) -> "NodeSocketNamespace":
        # Copy as parentSocket
        parent = self.socket_parent if parent is None else parent
        ns_copy = self.__class__(
            self.socket_name,
            parent=parent,
            link_limit=self.socket_link_limit,
            metadata=self.socket_metadata,
        )
        # Copy nested sockets
        for item in self._items:
            ns_copy._append(item._copy(parent=parent))
        return ns_copy

    def __iter__(self) -> object:
        for item in self._items:
            yield item

    def __getitem__(self, index: Union[int, str]) -> object:
        if isinstance(index, int):
            return self._items[index]
        elif isinstance(index, str):
            return self._get(index)

    def __contains__(self, name: str) -> bool:
        """Check if an item with the given name exists in the collection.

        Args:
            name (str): The name of the item to check.

        Returns:
            bool: True if the item exists, False otherwise.
        """
        return name in self._keys()

    def _append(self, item: object) -> None:
        """Append item into this collection."""
        if item.socket_name in self._keys():
            raise Exception(
                f"{item.socket_name} already exist, please choose another name."
            )
        self._items.append(item)
        # Set the item as an attribute on the instance
        setattr(self, item.socket_name, item)

    def _get(self, name: str) -> object:
        """Find item by name

        Args:
            name (str): _description_

        Returns:
            object: _description_
        """
        for item in self._items:
            if item.socket_name == name:
                return item
        raise AttributeError(
            f""""{name}" is not in the {self.__class__.__name__}.
Acceptable names are {self._keys()}. This collection belongs to {self.socket_parent}."""
        )

    def _keys(self) -> List[str]:
        keys = []
        for item in self._items:
            keys.append(item.socket_name)
        return keys

    def _clear(self) -> None:
        """Remove all items from this collection."""
        self._items = []

    def __delitem__(self, index: Union[int, List[int]]) -> None:
        del self._items[index]

    def _delete(self, name: str) -> None:
        """Delete item by name

        Args:
            name (str): _description_
        """
        for index, item in enumerate(self._items):
            if item.socket_name == name:
                del self._items[index]
                self._execute_post_deletion_hooks(item)
                return

    def __len__(self) -> int:
        return len(self._items)

    def __repr__(self) -> str:
        nested = [item.socket_name for item in self._items]
        return (
            f"{self.__class__.__name__}(name='{self.socket_name}', "
            f"sockets={nested})"
        )
