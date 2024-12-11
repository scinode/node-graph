from __future__ import annotations

from node_graph.property import NodeProperty
from typing import List, Optional, Dict, Any, TYPE_CHECKING, Union
from node_graph.utils import get_item_class
from node_graph.utils import get_entries
from node_graph.orm.mapping import type_mapping as node_graph_type_mapping


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

    _identifier: str = "BaseSocket"

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
        self._name: str = name
        self._node: Optional["Node"] = node
        self._parent: Optional["NodeSocketNamespace"] = parent
        self._links: List["NodeLink"] = []
        self._link_limit: int = link_limit
        self._metadata: Optional[dict] = metadata or {}

    @property
    def _full_name(self) -> str:
        if self._parent is not None:
            return f"{self._parent._full_name}.{self._name}"
        return self._name

    def _to_dict(self) -> Dict[str, Any]:
        """Export the socket to a dictionary for database storage."""
        data: Dict[str, Any] = {
            "name": self._name,
            "identifier": self._identifier,
            "link_limit": self._link_limit,
            "links": [],
            "metadata": self._metadata,
        }
        for link in self._links:
            if self._metadata.get("socket_type", "INPUT").upper() == "INPUT":
                data["links"].append(
                    {
                        "from_node": link.from_node.name,
                        "from_socket": link.from_socket._name,
                    }
                )
            else:
                data["links"].append(
                    {
                        "to_node": link.to_node.name,
                        "to_socket": link.to_socket._name,
                    }
                )

        # Conditionally add serializer/deserializer if they are defined
        if hasattr(self, "get_serialize") and callable(self.get_serialize):
            data["serialize"] = self.get_serialize()

        if hasattr(self, "get_deserialize") and callable(self.get_deserialize):
            data["deserialize"] = self.get_deserialize()
        return data


class NodeSocket(BaseSocket):

    _identifier: str = "NodeSocket"

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
        self.property: Optional[NodeProperty] = None
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
            name = self._name
        self.property = self._socket_property_class.new(
            identifier, name=name, data=kwargs
        )

    @property
    def value(self) -> Any:
        if self.property:
            return self.property.value
        return None

    @value.setter
    def value(self, value: Any) -> None:
        self._set_socket_value(value)

    def _set_socket_value(self, value: Any) -> None:
        if isinstance(value, BaseSocket):
            self._node.parent.add_link(value, self)
        elif self.property:
            self.property.value = value
        else:
            raise AttributeError(
                f"Socket '{self._name}' has no property to set a value."
            )

    def _to_dict(self):
        data = super()._to_dict()
        # data from property
        if self.property is not None:
            data["property"] = self.property.to_dict()
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
        node = self._node if node is None else node
        parent = self._parent if parent is None else parent
        socket_copy = self.__class__(
            name=self._name,
            node=node,
            parent=parent,
            link_limit=self._link_limit,
        )
        if self.property:
            socket_copy.property = self.property.copy()
        return socket_copy

    def __repr__(self) -> str:
        value = self.property.value if self.property else None
        return f"{self.__class__.__name__}(name='{self._name}', value={value})"


def check_identifier_name(identifier: str, pool: dict) -> None:
    import difflib

    if isinstance(identifier, str) and identifier.upper() not in pool:
        items = difflib.get_close_matches(identifier.upper(), pool)
        if len(items) == 0:
            msg = f"Identifier: {identifier} is not defined."
        else:
            msg = f"Identifier: {identifier} is not defined. Did you mean {', '.join(item.lower() for item in items)}?"
        raise ValueError(msg)


class NodeSocketNamespace(BaseSocket):
    """A NodeSocket that also acts as a namespace (collection) of other sockets."""

    _identifier: str = "node_graph.namespace"
    _type_mapping: dict = node_graph_type_mapping

    _RESERVED_NAMES = {
        "_RESERVED_NAMES",
        "_IDENTIFIER",
        "_VALUE",
        "_NAME",
        "_NODE",
        "_PARENT",
        "_LINKS",
        "_LINK_LIMIT",
        "_METADATA",
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
        #
        self._sockets: Dict[str, object] = {}
        self._parent = parent
        # one can specify the pool or entry_point to get the pool
        if pool is not None:
            self._socket_pool = pool
        elif entry_point is not None:
            self._socket_pool = get_entries(entry_point_name=entry_point)
        self._socket_is_dynamic = self._metadata.get("dynamic", False)

    def _new(
        self,
        identifier: Union[str, type] = None,
        name: Optional[str] = None,
        link_limit: int = 1,
        metadata: Optional[dict] = None,
        **kwargs: Any,
    ) -> object:

        identifier = identifier or self._type_mapping["default"]
        check_identifier_name(identifier, self._socket_pool)

        _names = name.split(".", 1)
        if len(_names) > 1:
            namespace = _names[0]
            if namespace not in self:
                # if the namespace is dynamic, create sub-sockets if it does not exist
                if self._socket_is_dynamic:
                    # the sub-socket should also be dynamic
                    self._new(
                        self._type_mapping["namespace"],
                        namespace,
                        metadata={"dynamic": True},
                    )
                else:
                    raise ValueError(
                        f"Namespace {namespace} does not exist in the socket collection."
                    )
            return self[namespace]._new(
                identifier,
                _names[1],
                metadata=metadata,
            )
        else:
            ItemClass = get_item_class(identifier, self._socket_pool, BaseSocket)
            item = ItemClass(
                name,
                node=self._node,
                parent=self,
                link_limit=link_limit,
                metadata=metadata,
                **kwargs,
            )
            self._append(item)
            return item

    @property
    def _value(self) -> Dict[str, Any]:

        data = {}
        for name, item in self._sockets.items():
            if isinstance(item, NodeSocketNamespace):
                value = item._value
                if value:
                    data[name] = value
            else:
                if item.value is not None:
                    data[name] = item.value
        return data

    @_value.setter
    def _value(self, value: Dict[str, Any]) -> None:
        self._set_socket_value(value)

    def _set_socket_value(self, value: Dict[str, Any] | NodeSocket) -> None:
        if isinstance(value, BaseSocket):
            self._node.parent.add_link(value, self)
        elif isinstance(value, dict):
            for key, val in value.items():
                if key not in self:
                    if self._socket_is_dynamic:
                        if isinstance(val, dict):
                            self._new(
                                self._type_mapping["namespace"],
                                key,
                                metadata={"dynamic": True},
                            )
                        else:
                            self._new(self._type_mapping["default"], key)
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
        data = super()._to_dict()
        data["sockets"] = {}
        # Add nested sockets information
        for item in self._sockets.values():
            data["sockets"][item._name] = item._to_dict()
        return data

    def _copy(self, parent: Optional["NodeSocket"] = None) -> "NodeSocketNamespace":
        # Copy as parentSocket
        parent = self._parent if parent is None else parent
        ns_copy = self.__class__(
            self._name,
            parent=parent,
            link_limit=self._link_limit,
            metadata=self._metadata,
        )
        # Copy nested sockets
        for item in self._sockets.values():
            ns_copy._append(item._copy(parent=parent))
        return ns_copy

    def __iter__(self) -> object:
        # Iterate over items in insertion order
        return iter(self._sockets.values())

    def __getitem__(self, key: Union[int, str]) -> object:
        if isinstance(key, int):
            # If indexing by int, convert dict keys to a list and index it
            return self._sockets[list(self._sockets.keys())[key]]
        elif isinstance(key, str):
            keys = key.split(".", 1)
            if keys[0] in self._sockets:
                item = self._sockets[keys[0]]
                if len(keys) > 1:
                    return item[keys[1]]
                return item
            raise AttributeError(
                f""""{key}" is not in the {self.__class__.__name__}.
Acceptable names are {self._get_keys()}. This collection belongs to {self._parent}."""
            )

    def __contains__(self, name: str) -> bool:
        """Check if an item with the given name exists in the collection.

        Args:
            name (str): The name of the item to check.

        Returns:
            bool: True if the item exists, False otherwise.
        """
        keys = name.split(".", 1)
        if keys[0] in self._sockets:
            if len(keys) > 1:
                return keys[1] in self._sockets[keys[0]]
            return True

    def _append(self, item: object) -> None:
        """Append item into this collection."""
        if item._name in self._sockets:
            raise ValueError(f"Name '{item._name}' already exists in the namespace.")
        if item._name.upper() in self._RESERVED_NAMES:
            raise ValueError(f"Name '{item._name}' is reserved by the namespace.")
        self._sockets[item._name] = item
        # Set the item as an attribute on the instance
        setattr(self, item._name, item)

    def _get(self, name: str) -> object:
        """Find item by name

        Args:
            name (str): _description_

        Returns:
            object: _description_
        """

    def _get_all_keys(self) -> List[str]:
        # keys in the collection, with the option to include nested keys
        keys = [item._full_name.split(".", 1)[1] for item in self._sockets.values()]
        for item in self._sockets.values():
            if isinstance(item, NodeSocketNamespace):
                keys.extend(item._get_all_keys())
            else:
                keys.append(item._full_name.split(".", 1)[1])
        return keys

    def _get_keys(self) -> List[str]:
        # keys in the collection, with the option to include nested keys
        return list(self._sockets.keys())

    def _clear(self) -> None:
        """Remove all items from this collection."""
        self._sockets = {}

    def __delitem__(self, index: Union[int, List[int], str]) -> None:
        # If index is int, convert _items to a list and remove by index
        if isinstance(index, str):
            self._sockets.pop(index)
        elif isinstance(index, int):
            key = list(self._sockets.keys())[index]
            self._sockets.pop(key)
        elif isinstance(index, list):
            keys = list(self._sockets.keys())
            for i in sorted(index, reverse=True):
                key = keys[i]
                self._sockets.pop(key)
        else:
            raise ValueError(
                f"Invalid index type for __delitem__: {index}, expected int or str, or list of int."
            )

    def __len__(self) -> int:
        return len(self._sockets)

    def __repr__(self) -> str:
        nested = list(self._sockets.keys())
        return f"{self.__class__.__name__}(name='{self._name}', " f"sockets={nested})"
