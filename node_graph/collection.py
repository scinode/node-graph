import importlib
from node_graph.utils import get_entries
from typing import List, Union, Optional, Callable
import difflib


class Collection:
    """Collection of instances of a property.
    Like an extended list, with the functions: new, find, delete, clear.

    Attributes:
        path (str): path to import the module.
    """

    path: str = ""
    parent_name: str = "parent"

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
        self._items: List[object] = []
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
        for item in self._items:
            yield item

    def __getitem__(self, index: Union[int, str]) -> object:
        if isinstance(index, int):
            return self._items[index]
        elif isinstance(index, str):
            return self.get(index)

    def __getattr__(self, name):
        if self._items:
            return self.get(name)
        else:
            raise AttributeError(f"{name} not available in an empty collection")

    def get_inner_id(self) -> int:
        """Get the inner id for the next item.

        inner_id is the index of the item in the collection.
        """
        inner_id = max([0] + [item.inner_id for item in self._items]) + 1
        return inner_id

    def new(self, identifier: str, name: Optional[str] = None) -> object:
        """Add new item into this collection.

        Args:
            identifier (str): Class for the new item
            name (str, optional): name of the new item. Defaults to None.

        Returns:
            object: A instance of the class.
        """
        module = importlib.import_module(self.path)
        ItemClass = getattr(module, identifier)
        item = ItemClass(name)
        setattr(item, self.parent_name, self.parent)
        self.append(item)
        return item

    def append(self, item: object) -> None:
        """Append item into this collection."""
        if item.name in self.keys():
            raise Exception(f"{item.name} already exist, please choose another name.")
        item.inner_id = self.get_inner_id()
        setattr(item, "parent", self.parent)
        self._items.append(item)

    def extend(self, items: List[object]) -> None:
        new_names = set([item.name for item in items])
        conflict_names = set(self.keys()).intersection(new_names)
        if len(conflict_names) > 0:
            raise Exception(
                f"{conflict_names} already exist, please choose another names."
            )
        for item in items:
            self.append(item)

    def get(self, name: str) -> object:
        """Find item by name

        Args:
            name (str): _description_

        Returns:
            object: _description_
        """
        for item in self._items:
            if item.name == name:
                return item
        raise Exception(
            f""""{name}" is not in the {self.__class__.__name__}.
Acceptable names are {self.keys()}. This collection belongs to {self.parent}."""
        )

    def get_by_uuid(self, uuid: str) -> Optional[object]:
        """Find item by uuid

        Args:
            uuid (str): _description_

        Returns:
            object: _description_
        """
        for item in self._items:
            if item.uuid == uuid:
                return item
        return None

    def keys(self) -> List[str]:
        keys = []
        for item in self._items:
            keys.append(item.name)
        return keys

    def clear(self) -> None:
        """Remove all items from this collection."""
        self._items = []

    def __delitem__(self, index: Union[int, List[int]]) -> None:
        del self._items[index]

    def delete(self, name: str) -> None:
        """Delete item by name

        Args:
            name (str): _description_
        """
        for index, item in enumerate(self._items):
            if item.name == name:
                del self._items[index]
                self.execute_post_deletion_hooks(item)
                return

    def __len__(self) -> int:
        return len(self._items)

    def __repr__(self) -> str:
        s = ""
        s += "Collection()\n"
        return s

    def copy(self, parent: Optional[object] = None) -> object:
        coll = self.__class__(parent=parent)
        coll._items = [item.copy() for item in self._items]
        return coll

    def execute_post_creation_hooks(self, item: object) -> None:
        """Execute all functions in post_creation_hooks with the given item."""
        for func in self.post_creation_hooks:
            func(self, item)

    def execute_post_deletion_hooks(self, item: object) -> None:
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
                msg = "Identifier: {} is not defined.".format(identifier)
            else:
                msg = "Identifier: {} is not defined. Do you mean {}".format(
                    identifier, ", ".join(items)
                )
            raise Exception(msg)
        if len(args) > 2 and args[2] in args[0].keys():
            raise Exception(
                "{} already exist, please choose another name.".format(args[2])
            )
        if kwargs.get("name", None) in args[0].keys():
            raise Exception(
                "{} already exist, please choose another name.".format(args[1])
            )
        item = func(*args, **kwargs)
        return item

    return wrapper_func


class NodeCollection(Collection):
    """Node colleciton"""

    parent_name = "node_graph"

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
    def new(
        self,
        identifier: Union[str, type],
        name: Optional[str] = None,
        uuid: Optional[str] = None,
        **kwargs,
    ) -> object:
        from node_graph.node import Node

        inner_id = self.get_inner_id()
        if isinstance(identifier, str):
            ItemClass = self.pool[identifier.upper()]
        elif isinstance(identifier, type) and issubclass(identifier, Node):
            ItemClass = identifier
        elif isinstance(getattr(identifier, "node", None), type) and issubclass(
            identifier.node, Node
        ):
            ItemClass = identifier.node
        else:
            raise Exception(f"Identifier {identifier} is not a node or node name.")
        item = ItemClass(inner_id=inner_id, name=name, uuid=uuid, parent=self.parent)
        self.append(item)
        item.set(kwargs)
        # Execute post creation hooks
        self.execute_post_creation_hooks(item)
        return item

    def copy(self, parent: Optional[object] = None) -> object:
        coll = self.__class__(parent=parent)
        coll._items = [item.copy(parent=parent) for item in self._items]
        return coll

    def __repr__(self) -> str:
        s = ""
        parent_name = self.parent.name if self.parent else ""
        s += f'NodeCollection(parent = "{parent_name}", nodes = ['
        s += ", ".join([f'"{x}"' for x in self.keys()])
        s += "])"
        return s


class PropertyCollection(Collection):
    """Property colleciton"""

    parent_name = "node"

    def __init__(
        self,
        parent: Optional[object] = None,
        pool: Optional[object] = None,
        entry_point: Optional[str] = "node_graph.property",
    ) -> None:
        super().__init__(parent, pool=pool, entry_point=entry_point)

    @decorator_check_identifier_name
    def new(
        self, identifier: Union[str, type], name: Optional[str] = None, **kwargs
    ) -> object:
        from node_graph.property import NodeProperty

        if isinstance(identifier, str):
            ItemClass = self.pool[identifier.upper()]
        elif isinstance(identifier, type) and issubclass(identifier, NodeProperty):
            ItemClass = identifier
        else:
            raise Exception(
                f"Identifier {identifier} is not a property or property name."
            )
        item = ItemClass(name, **kwargs)
        self.append(item)
        return item

    def __repr__(self) -> str:
        s = ""
        node_name = self.parent.name if self.parent else ""
        s += f'PropertyCollection(node = "{node_name}", properties = ['
        s += ", ".join([f'"{x}"' for x in self.keys()])
        s += "])"
        return s


class InputSocketCollection(Collection):
    """Input Socket colleciton"""

    parent_name = "node"

    def __init__(
        self,
        parent: Optional[object] = None,
        pool: Optional[object] = None,
        entry_point: Optional[str] = "node_graph.socket",
    ) -> None:
        super().__init__(parent, pool=pool, entry_point=entry_point)

    @decorator_check_identifier_name
    def new(
        self, identifier: Union[str, type], name: Optional[str] = None, **kwargs
    ) -> object:
        from node_graph.socket import NodeSocket

        if isinstance(identifier, str):
            ItemClass = self.pool[identifier.upper()]
        elif isinstance(identifier, type) and issubclass(identifier, NodeSocket):
            ItemClass = identifier
        else:
            raise Exception(f"Identifier {identifier} is not a socket or socket name.")
        inner_id = self.get_inner_id()
        item = ItemClass(name, type="INPUT", index=inner_id, **kwargs)
        self.append(item)
        return item

    def copy(self, parent: Optional[object] = None, is_ref: bool = False) -> object:
        """Copy the input socket collection.

        Args:
            parent (Node, optional): Node that the socket bound to. Defaults to None.
            is_ref (bool, optional): is a reference socket. Defaults to False.

        Returns:
            Collection: _description_
        """
        coll = self.__class__(parent=parent)
        coll._items = [item.copy(node=parent, is_ref=is_ref) for item in self._items]
        return coll

    def __repr__(self) -> str:
        s = ""
        node_name = self.parent.name if self.parent else ""
        s += f'InputCollection(node = "{node_name}", sockets = ['
        s += ", ".join([f'"{x}"' for x in self.keys()])
        s += "])"
        return s


class OutputSocketCollection(Collection):
    """Output Socket colleciton"""

    parent_name = "node"

    def __init__(
        self,
        parent: Optional[object] = None,
        pool: Optional[object] = None,
        entry_point: Optional[str] = "node_graph.socket",
    ) -> None:
        super().__init__(parent, pool=pool, entry_point=entry_point)

    @decorator_check_identifier_name
    def new(self, identifier: Union[str, type], name: Optional[str] = None) -> object:
        from node_graph.socket import NodeSocket

        if isinstance(identifier, str):
            ItemClass = self.pool[identifier.upper()]
        elif isinstance(identifier, type) and issubclass(identifier, NodeSocket):
            ItemClass = identifier
        else:
            raise Exception(f"Identifier {identifier} is not a socket or socket name.")
        item = ItemClass(name, type="OUTPUT", index=len(self._items))
        self.append(item)
        return item

    def copy(self, parent: Optional[object] = None, is_ref: bool = False) -> object:
        coll = self.__class__(parent=parent)
        coll._items = [item.copy(node=parent, is_ref=is_ref) for item in self._items]
        return coll

    def __repr__(self) -> str:
        s = ""
        node_name = self.parent.name if self.parent else ""
        s += f'OutputCollection(node = "{node_name}", sockets = ['
        s += ", ".join([f'"{x}"' for x in self.keys()])
        s += "])"
        return s


class LinkCollection(Collection):
    """Link colleciton"""

    def __init__(self, parent: object) -> None:
        super().__init__(parent)

    def new(self, input: object, output: object, type: int = 1) -> object:
        from node_graph.link import NodeLink

        item = NodeLink(input, output)
        self.append(item)
        # Execute post creation hooks
        self.execute_post_creation_hooks(item)
        return item

    def __delitem__(self, index: Union[int, List[int]]) -> None:
        """Delete link from this collection.

        First remove the link in the nodes by calling the unmount method.

        Args:
            index (_type_): _description_
        """
        if isinstance(index, (list, tuple)):
            for i in index:
                self._items[i].unmount()
            self._items = [item for i, item in enumerate(self._items) if i not in index]
            return
        self._items[index].unmount()
        del self._items[index]

    def clear(self) -> None:
        """Remove all links from this collection.
        And remove the link in the nodes.
        """
        for item in self._items:
            item.unmount()
        self._items = []

    def __repr__(self) -> str:
        s = ""
        s += "LinkCollection({} links)\n".format(len(self))
        return s
