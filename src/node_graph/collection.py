from __future__ import annotations
from typing import TYPE_CHECKING, List, Union, Optional, Callable, Dict, Type
import difflib
from importlib.metadata import entry_points, EntryPoint
import sys
import logging

if TYPE_CHECKING:
    from node_graph.node import Node
    from node_graph.nodes.factory.base import BaseNodeFactory

logger = logging.getLogger(__name__)


def get_entries(entry_point_name: str) -> Dict[str, EntryPoint]:
    """Get entries from the entry point."""
    pool: Dict[str, EntryPoint] = {}
    eps = entry_points()
    if sys.version_info >= (3, 10):
        group = eps.select(group=entry_point_name)
    else:
        group = eps.get(entry_point_name, [])
    for entry_point in group:
        if entry_point.name.upper() not in pool:
            pool[entry_point.name.upper()] = entry_point
        else:
            raise Exception("Entry: {} is already registered.".format(entry_point.name))
    return pool


def get_item_class(
    identifier: EntryPoint | Node | BaseNodeFactory,
    pool: Dict[str, EntryPoint],
    base_class: Type[Node] = None,
    factory_class: Type[BaseNodeFactory] = None,
    inputs: Optional[Dict] = None,
) -> Node:
    """Get the item class from the identifier."""

    from node_graph.node import Node
    from node_graph.nodes.factory.base import BaseNodeFactory

    base_class = base_class or Node
    factory_class = factory_class or BaseNodeFactory

    if isinstance(identifier, str):
        identifier = pool[identifier.lower()].load()
    # to support different versions of entry points
    elif identifier.__class__.__name__ == "EntryPoint":
        identifier = identifier.load()
    if isinstance(identifier, type):
        if issubclass(identifier, base_class):
            ItemClass = identifier
        elif issubclass(identifier, factory_class):
            ItemClass = identifier.create_class(inputs)
        else:
            raise Exception(
                f"Identifier {identifier} is not a valid {base_class.__name__} class or entry point."
            )
    elif isinstance(getattr(identifier, "_NodeCls", None), type) and issubclass(
        identifier._NodeCls, base_class
    ):
        ItemClass = identifier._NodeCls
    else:
        raise Exception(
            f"Identifier {identifier} is not a valid {base_class.__name__} class or entry point."
        )
    return ItemClass


class Namespace:
    """A simple recursive namespace that allows attribute-based access to nested dictionaries, with tab completion."""

    def __init__(self):
        self._data = {}

    def __getattr__(self, name: str) -> EntryPoint:
        if name in super().__getattribute__("_data"):
            return super().__getattribute__("_data")[name]
        raise AttributeError(f"Namespace has no attribute {name!r}")

    def __setattr__(self, name: str, value: Namespace | EntryPoint) -> None:
        if name == "_data":
            super().__setattr__(name, value)
        else:
            self._data[name] = value

    def __dir__(self):
        """Enable tab completion by returning all available attributes."""
        return list(self._data.keys())

    def __repr__(self):
        return f"Namespace({self._data})"

    def __contains__(self, key: str) -> bool:
        """Allow checking if a key exists, including nested keys."""
        parts = key.split(".")  # Handle nested keys
        current = self
        for part in parts:
            if part in current._data:
                current = current._data[part]
            else:
                return False
        return True  # If all parts exist, return True

    def __iter__(self):
        """Allow iteration over stored items."""
        return iter(self._data.items())

    def __getitem__(self, key: str) -> EntryPoint | Namespace:
        """Allow dictionary-like access and support nested keys."""
        parts = key.split(".")  # Handle nested keys
        current = self
        for part in parts:
            if part in current._data:
                current = current._data[part]
            else:
                raise KeyError(f"Key {key!r} not found in Namespace")
        return current

    def __setitem__(self, key: str, value: EntryPoint | Namespace) -> None:
        """Allow dictionary-like setting and support nested keys."""
        parts = key.split(".")  # Handle nested keys
        current = self
        for part in parts[:-1]:  # Traverse or create nested structures
            if part not in current._data:
                current._data[part] = Namespace()
            current = current._data[part]
        current._data[parts[-1]] = value  # Set the final value

    def _keys(self, prefix="") -> list[str]:
        """Return all keys, including nested keys, using dot notation."""
        all_keys = []
        for key, value in self._data.items():
            full_key = f"{prefix}.{key}" if prefix else key
            all_keys.append(full_key)
            if isinstance(value, Namespace):  # Recursively collect nested keys
                all_keys.extend(value._keys(prefix=full_key))
        return all_keys


class EntryPointPool:
    """
    NodePool is a hierarchical namespace that loads nodes from entry points.
    This version is designed to be used as an instance and supports tab completion.
    """

    def __init__(self, entry_point_group: str):
        self._nodes = Namespace()
        self._is_loaded = False
        self._load_nodes(entry_point_group)

    def _load_nodes(self, entry_point_group: str) -> None:
        """Loads nodes into the internal hierarchical dictionary, if not already loaded."""
        if self._is_loaded:
            return

        eps = entry_points()

        if sys.version_info >= (3, 10):
            group = eps.select(group=entry_point_group)
        else:
            group = eps.get(entry_point_group, [])

        for ep in group:
            key_parts = ep.name.lower().split(".")  # Use '.' to define nested levels
            current_level = self._nodes

            # Create the nested namespace structure
            for part in key_parts[:-1]:
                if not hasattr(current_level, part):
                    setattr(current_level, part, Namespace())
                current_level = getattr(current_level, part)

            final_key = key_parts[-1]
            if hasattr(current_level, final_key):
                raise Exception(f"Duplicate entry point name detected: {ep.name!r}")

            setattr(current_level, final_key, ep)

        self._is_loaded = True

    def __getattr__(self, name: str) -> EntryPoint:
        """Allow direct access to nodes via instance attributes."""
        return getattr(super().__getattribute__("_nodes"), name)

    def __dir__(self):
        """Enable tab completion for the node pool instance."""
        return dir(self._nodes)

    def __repr__(self):
        return f"NodePool({self._nodes})"

    def __contains__(self, key: str) -> bool:
        """Allow checking if a key exists in the node pool."""
        return key in self._nodes

    def __iter__(self):
        """Allow iteration over stored items."""
        return iter(self._nodes)

    def __getitem__(self, key: str) -> EntryPoint:
        """Allow dictionary-like access to the nodes."""
        return self._nodes[key]

    def __setitem__(self, key: str, value: EntryPoint | Namespace) -> None:
        """Allow dictionary-like setting and support nested keys."""
        self._nodes[key] = value

    def _keys(self) -> list[str]:
        """Return all keys, including nested keys."""
        return self._nodes._keys()


class Collection:
    """Collection of instances of a property.
    Like an extended list, with the functions: new, find, delete, clear.

    """

    def __init__(
        self,
        parent: Optional[object] = None,
        pool: Optional[object] = None,
        entry_point: Optional[str] = None,
        post_creation_hooks: Optional[List[Callable]] = None,
        post_deletion_hooks: Optional[List[Callable]] = None,
    ) -> None:
        """Init a collection instance

        Args:
            parent (object, optional): object this collection belongs to.
        """
        self._items: List[object] = {}
        self.parent = parent
        # one can specify the pool or entry_point to get the pool
        # if pool is not None, entry_point will be ignored, e.g., Link has no pool
        if pool is not None:
            self.pool = pool
        elif entry_point is not None:
            self.pool = get_entries(entry_point_name=entry_point)
        self.post_creation_hooks = post_creation_hooks or []
        self.post_deletion_hooks = post_deletion_hooks or []

    def __iter__(self) -> object:
        # Iterate over items in insertion order
        return iter(self._items.values())

    def __getitem__(self, index: Union[int, str]) -> object:
        if isinstance(index, int):
            # If indexing by int, convert dict keys to a list and index it
            return self._items[list(self._items.keys())[index]]
        elif isinstance(index, str):
            return self._items[index]

    def __dir__(self):
        return sorted(set(self._get_keys()))

    def __contains__(self, name: str) -> bool:
        """Check if an item with the given name exists in the collection.

        Args:
            name (str): The name of the item to check.

        Returns:
            bool: True if the item exists, False otherwise.
        """
        return name in self._items

    def _generate_item_name(self, item_class) -> int:
        """Generate a new name for the item based on the given name and
        the number of items in the collection.
        """
        if item_class.default_name is None:
            name = item_class.identifier.split(".")[-1]
        else:
            name = item_class.default_name
        if name not in self._items:
            return name
        index = 1
        new_name = f"{name}{index}"
        while new_name in self._items:
            index += 1
            new_name = f"{name}{index}"
        return new_name

    def _new(self) -> object:
        """Add new item into this collection."""
        raise NotImplementedError("new method is not implemented.")

    def _append(self, item: object) -> None:
        """Append item into this collection."""
        if item.name in self._items:
            raise Exception(f"{item.name} already exists, please choose another name.")
        self._items[item.name] = item
        # Set the item as an attribute on the instance
        setattr(self, item.name, item)
        setattr(item, "_coll", self)

    def _extend(self, items: List[object]) -> None:
        new_names = set([item.name for item in items])
        conflict_names = set(self._get_keys()).intersection(new_names)
        if len(conflict_names) > 0:
            raise Exception(
                f"{conflict_names} already exist, please choose another names."
            )
        for item in items:
            self._append(item)

    def _get(self, name: str) -> object:
        """Find item by name

        Args:
            name (str): _description_

        Returns:
            object: _description_
        """
        if name in self._items:
            return self._items[name]
        raise AttributeError(
            f""""{name}" is not in the {self.__class__.__name__}.
Acceptable names are {self._get_keys()}. This collection belongs to {self._parent}."""
        )

    def _get_by_uuid(self, uuid: str) -> Optional[object]:
        """Find item by uuid

        Args:
            uuid (str): _description_

        Returns:
            object: _description_
        """
        for item in self._items.values():
            if item.uuid == uuid:
                return item
        return None

    def _get_keys(self) -> List[str]:
        return list(self._items.keys())

    def _clear(self) -> None:
        """Remove all items from this collection."""
        self._items = {}

    def __delitem__(self, index: Union[int, List[int], str]) -> None:
        # If index is int, convert _items to a list and remove by index
        if isinstance(index, str):
            self._items.pop(index)
        elif isinstance(index, int):
            key = list(self._items.keys())[index]
            self._items.pop(key)
        elif isinstance(index, list):
            keys = list(self._items.keys())
            for i in sorted(index, reverse=True):
                key = keys[i]
                self._items.pop(key)
        else:
            raise ValueError(
                f"Invalid index type for __delitem__: {index}, expected int or str, or list of int."
            )

    def _pop(self, index: Union[int, str]) -> object:
        if isinstance(index, int):
            key = list(self._items.keys())[index]
            return self._items.pop(key)
        return self._items.pop(index)

    def __len__(self) -> int:
        return len(self._items)

    def __repr__(self) -> str:
        s = ""
        s += "Collection()\n"
        return s

    def _copy(self, parent: Optional[object] = None) -> object:
        coll = self.__class__(parent=parent)
        coll._items = {key: item.copy() for key, item in self._items.items()}
        return coll

    def _execute_post_creation_hooks(self, item: object) -> None:
        """Execute all functions in post_creation_hooks with the given item."""
        for func in self.post_creation_hooks:
            func(self, item)

    def _execute_post_deletion_hooks(self, item: object) -> None:
        """Execute all functions in post_deletion_hooks with the given item."""
        for func in self.post_deletion_hooks:
            func(self, item)


def decorator_check_identifier_name(func: Callable) -> Callable:
    """Check identifier and name exist or not.

    Args:
        func (_type_): _description_
    """

    def wrapper_func(*args, **kwargs):
        from node_graph.utils import valid_name_string

        identifier = args[1]
        if isinstance(identifier, str) and identifier.lower() not in args[0].pool:
            items = difflib.get_close_matches(identifier.lower(), args[0].pool._keys())
            if len(items) == 0:
                msg = f"Identifier: {identifier} is not defined."
            else:
                msg = f"Identifier: {identifier} is not defined. Did you mean {', '.join(item.lower() for item in items)}?"
            raise ValueError(msg)
        name = None
        if len(args) > 2:
            name = args[2]
        if kwargs.get("name", None):
            name = kwargs.get("name")
        if name is not None:
            valid_name_string(name)
            if name in args[0]._get_keys():
                raise ValueError(f"{name} already exists, please choose another name.")
        item = func(*args, **kwargs)
        return item

    return wrapper_func


class NodeCollection(Collection):
    """Node colleciton"""

    def __init__(
        self,
        graph: Optional[object] = None,
        pool: Optional[object] = None,
        entry_point: Optional[str] = "node_graph.node",
        post_creation_hooks: Optional[List[Callable]] = None,
    ) -> None:
        super().__init__(
            parent=graph,
            pool=pool,
            entry_point=entry_point,
            post_creation_hooks=post_creation_hooks,
        )

    @decorator_check_identifier_name
    def _new(
        self,
        identifier: Union[str, type],
        name: Optional[str] = None,
        uuid: Optional[str] = None,
        _metadata: Optional[dict] = None,
        _executor: Optional[dict] = None,
        **kwargs,
    ) -> Node:
        from node_graph.node import Node
        from node_graph.nodes.factory.base import BaseNodeFactory

        ItemClass = get_item_class(
            identifier, self.pool, Node, BaseNodeFactory, inputs=kwargs
        )
        name = name or self._generate_item_name(ItemClass)
        node = ItemClass(
            name=name,
            uuid=uuid,
            graph=self.parent,
            metadata=_metadata,
            executor=_executor,
        )
        self._append(node)
        node.set(kwargs)
        logger.debug(f"Created new node '{node.name}' with identifier={identifier}.")
        # Execute post creation hooks
        self._execute_post_creation_hooks(node)
        return node

    def _append(self, item: object) -> None:
        """Append item into this collection."""
        super()._append(item)
        setattr(item, "graph", self.parent)

    def _copy(self, graph: Optional[object] = None) -> object:
        coll = self.__class__(graph=graph)
        for key, item in self._items.items():
            coll._append(item.copy(graph=graph))
        return coll

    def __repr__(self) -> str:
        s = ""
        parent_name = self.parent.name if self.parent else ""
        s += f'NodeCollection(parent = "{parent_name}", nodes = ['
        s += ", ".join([f'"{x}"' for x in self._get_keys()])
        s += "])"
        return s


class PropertyCollection(Collection):
    """Property colleciton"""

    def __init__(
        self,
        parent: Optional[object] = None,
        pool: Optional[object] = None,
        entry_point: Optional[str] = "node_graph.property",
    ) -> None:
        super().__init__(parent, pool=pool, entry_point=entry_point)

    @decorator_check_identifier_name
    def _new(
        self, identifier: Union[str, type], name: Optional[str] = None, **kwargs
    ) -> object:
        from node_graph.property import NodeProperty

        ItemClass = get_item_class(identifier, self.pool, NodeProperty)
        item = ItemClass(name, **kwargs)
        self._append(item)
        return item

    def __repr__(self) -> str:
        s = ""
        node_name = self.parent.name if self.parent else ""
        s += f'PropertyCollection(node = "{node_name}", properties = ['
        s += ", ".join([f'"{x}"' for x in self._get_keys()])
        s += "])"
        return s


class LinkCollection(Collection):
    """Link colleciton"""

    def __init__(self, parent: object) -> None:
        super().__init__(parent)

    def _new(self, input: object, output: object, type: int = 1) -> object:
        from node_graph.link import NodeLink

        item = NodeLink(input, output)
        self._append(item)
        # Execute post creation hooks
        self._execute_post_creation_hooks(item)
        return item

    def __delitem__(self, index: Union[int, List[int], str]) -> None:
        # If index is int, convert _items to a list and remove by index
        if isinstance(index, str):
            self._items[index].unmount()
            self._items.pop(index)
        elif isinstance(index, int):
            key = list(self._items.keys())[index]
            self._items[key].unmount()
            self._items.pop(key)
        elif isinstance(index, list):
            keys = list(self._items.keys())
            for i in sorted(index, reverse=True):
                key = keys[i]
                self._items[key].unmount()
                self._items.pop(key)
        else:
            raise ValueError(
                f"Invalid index type for __delitem__: {index}, expected int or str, or list of int."
            )

    def clear(self) -> None:
        """Remove all links from this collection.
        And remove the link in the nodes.
        """
        for item in self._items.values():
            item.unmount()
        self._items = {}

    def __repr__(self) -> str:
        s = ""
        s += "LinkCollection({} links)\n".format(len(self))
        return s
