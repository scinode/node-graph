from node_graph.utils import get_entries
from typing import List, Union, Optional, Callable
import difflib
from node_graph.utils import get_item_class


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

    def _get_list_index(self) -> int:
        """Get the inner id for the next item.

        list_index is the index of the item in the collection.
        """
        list_index = max([0] + [item.list_index for item in self._items.values()]) + 1
        return list_index

    def _new(self, identifier: str, name: Optional[str] = None) -> object:
        """Add new item into this collection."""
        raise NotImplementedError("new method is not implemented.")

    def _append(self, item: object) -> None:
        """Append item into this collection."""
        if item.name in self._items:
            raise Exception(f"{item.name} already exists, please choose another name.")
        self._items[item.name] = item
        # Set the item as an attribute on the instance
        setattr(self, item.name, item)
        setattr(item, "parent", self.parent)

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

    def pop(self, index: Union[int, str]) -> object:
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

        identifier = args[1]
        if isinstance(identifier, str) and identifier.upper() not in args[0].pool:
            items = difflib.get_close_matches(identifier.upper(), args[0].pool)
            if len(items) == 0:
                msg = f"Identifier: {identifier} is not defined."
            else:
                msg = f"Identifier: {identifier} is not defined. Did you mean {', '.join(item.lower() for item in items)}?"
            raise ValueError(msg)
        if len(args) > 2 and args[2] in args[0]._get_keys():
            raise ValueError(f"{args[2]} already exists, please choose another name.")
        if kwargs.get("name", None) in args[0]._get_keys():
            raise ValueError(
                f"{kwargs.get('name')} already exists, please choose another name."
            )
        item = func(*args, **kwargs)
        return item

    return wrapper_func


class NodeCollection(Collection):
    """Node colleciton"""

    def __init__(
        self,
        parent: Optional[object] = None,
        pool: Optional[object] = None,
        entry_point: Optional[str] = "node_graph.node",
        post_creation_hooks: Optional[List[Callable]] = None,
    ) -> None:
        super().__init__(
            parent,
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
    ) -> object:
        from node_graph.node import Node

        list_index = self._get_list_index()
        ItemClass = get_item_class(identifier, self.pool, Node)
        item = ItemClass(
            list_index=list_index,
            name=name,
            uuid=uuid,
            parent=self.parent,
            metadata=_metadata,
            executor=_executor,
        )
        self._append(item)
        item.set(kwargs)
        # Execute post creation hooks
        self._execute_post_creation_hooks(item)
        return item

    def _copy(self, parent: Optional[object] = None) -> object:
        coll = self.__class__(parent=parent)
        coll._items = {
            key: item.copy(parent=parent) for key, item in self._items.items()
        }
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
