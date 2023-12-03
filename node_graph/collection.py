import importlib
from node_graph.utils import get_entries


class Collection:
    """Collection of instances of a property.
    Like an extended list, with the functions: new, find, delete, clear.

    Attributes:
        path (str): path to import the module.
    """

    path: str = ""
    parent_name: str = "parent"

    def __init__(self, parent=None, pool=None, entry_point=None) -> None:
        """Init a collection instance

        Args:
            parent (unknow): object this collection belongs to.
        """
        self._items = []
        self.parent = parent
        # one can specify the pool or entry_point to get the pool
        # if pool is not None, entry_point will be ignored, e.g., Link has no pool
        if pool is not None:
            self.pool = pool
        elif entry_point is not None:
            self.pool = get_entries(entry_point_name=entry_point)

    def __iter__(self):
        for item in self._items:
            yield item

    def __getitem__(self, index):
        if isinstance(index, int):
            return self._items[index]
        elif isinstance(index, str):
            return self.get(index)

    def get_inner_id(self):
        """Get the inner id for the next item.

        inner_id is the index of the item in the collection.
        """
        inner_id = max([0] + [item.inner_id for item in self._items]) + 1
        return inner_id

    def new(self, identifier, name=None):
        """Add new item into this collection.

        Args:
            identifier (str): Class for the new item
            name (str, optional): name of the new item. Defaults to None.

        Returns:
            Class Object: A instance of the class.
        """
        module = importlib.import_module(self.path)
        ItemClass = getattr(module, identifier)
        item = ItemClass(name)
        setattr(item, self.parent_name, self.parent)
        self.append(item)
        return item

    def append(self, item):
        """Append item into this collection."""
        if item.name in self.keys():
            raise Exception(f"{item.name} already exist, please choose another name.")
        item.inner_id = self.get_inner_id()
        setattr(item, "parent", self.parent)
        self._items.append(item)

    def extend(self, items):
        new_names = set([item.name for item in items])
        conflict_names = set(self.keys()).intersection(new_names)
        if len(conflict_names) > 0:
            raise Exception(
                f"{conflict_names} already exist, please choose another names."
            )
        for item in items:
            self.append(item)

    def get(self, name):
        """Find item by name

        Args:
            name (str): _description_

        Returns:
            _type_: _description_
        """
        for item in self._items:
            if item.name == name:
                return item
        raise Exception(
            f'"{name}" is not in the {self.__class__.__name__}. Acceptable names are {self.keys()}. This collection belongs to {self.parent}.'
        )

    def get_by_uuid(self, uuid):
        """Find item by uuid

        Args:
            uuid (str): _description_

        Returns:
            _type_: _description_
        """
        for item in self._items:
            if item.uuid == uuid:
                return item
        return None

    def keys(self):
        keys = []
        for item in self._items:
            keys.append(item.name)
        return keys

    def clear(self):
        """Remove all items from this collection."""
        self._items = []

    def __delitem__(self, index):
        del self._items[index]

    def delete(self, name):
        """Delete item by name

        Args:
            name (str): _description_
        """
        for index, item in enumerate(self._items):
            if item.name == name:
                del self._items[index]
                return

    def __len__(self):
        return len(self._items)

    def __repr__(self) -> str:
        s = ""
        s += "Collection()\n"
        return s

    def copy(self, parent=None):
        coll = self.__class__(parent=parent)
        coll._items = [item.copy() for item in self._items]
        return coll


def decorator_check_identifier_name(func):
    """Check identifier and name exist or not.

    Args:
        func (_type_): _description_
    """

    def wrapper_func(*args, **kwargs):
        import difflib

        identifier = args[1]
        if isinstance(identifier, str) and identifier not in args[0].pool:
            items = difflib.get_close_matches(identifier, args[0].pool)
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

    def __init__(self, parent=None, pool=None, entry_point="node_graph.node") -> None:
        super().__init__(parent, pool=pool, entry_point=entry_point)

    @decorator_check_identifier_name
    def new(self, identifier, name=None, uuid=None, **kwargs):
        from node_graph.node import Node

        inner_id = self.get_inner_id()
        if isinstance(identifier, str):
            ItemClass = self.pool[identifier]
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
        return item

    def copy(self, parent=None):
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
        self, parent=None, pool=None, entry_point="node_graph.property"
    ) -> None:
        super().__init__(parent, pool=pool, entry_point=entry_point)

    @decorator_check_identifier_name
    def new(self, identifier, name=None, **kwargs):

        ItemClass = self.pool[identifier]
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

    def __init__(self, parent=None, pool=None, entry_point="node_graph.socket") -> None:
        super().__init__(parent, pool=pool, entry_point=entry_point)

    @decorator_check_identifier_name
    def new(self, identifier, name=None, **kwargs):

        ItemClass = self.pool[identifier]
        inner_id = self.get_inner_id()
        item = ItemClass(name, type="INPUT", index=inner_id, **kwargs)
        self.append(item)
        return item

    def copy(self, parent=None, is_ref=False):
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

    def __init__(self, parent=None, pool=None, entry_point="node_graph.socket") -> None:
        super().__init__(parent, pool=pool, entry_point=entry_point)

    @decorator_check_identifier_name
    def new(self, identifier, name=None):

        ItemClass = self.pool[identifier]
        item = ItemClass(name, type="OUTPUT", index=len(self._items))
        self.append(item)
        return item

    def copy(self, parent=None, is_ref=False):
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

    def __init__(self, parent) -> None:
        super().__init__(parent)

    def new(self, input, output, type=1):
        from node_graph.link import NodeLink

        item = NodeLink(input, output)
        self.append(item)

    def __delitem__(self, index):
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

    def clear(self):
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
