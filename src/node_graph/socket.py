from __future__ import annotations
from node_graph.collection import DependencyCollection
from node_graph.property import NodeProperty
from typing import Any, Dict, List, Optional, TYPE_CHECKING, Union
from node_graph.collection import get_item_class
from dataclasses import MISSING, dataclass, field
from node_graph.orm.mapping import type_mapping
from node_graph.registry import EntryPointPool
import wrapt

if TYPE_CHECKING:
    from node_graph.node import Node
    from node_graph.link import NodeLink
    from node_graph.node_graph import NodeGraph


def op_add(x, y):
    return x + y


def op_sub(x, y):
    return x - y


def op_mul(x, y):
    return x * y


def op_truediv(x, y):
    return x / y


def op_pow(x, y):
    return x**y


def op_mod(x, y):
    return x % y


def op_floordiv(x, y):
    return x // y


# comparison operations
def op_lt(x, y):
    return x < y


def op_gt(x, y):
    return x > y


def op_le(x, y):
    return x <= y


def op_ge(x, y):
    return x >= y


def op_eq(x, y):
    return x == y


def op_ne(x, y):
    return x != y


def _raise_illegal(sock, what: str, tips: list[str]):
    from .errors import GraphDeferredIllegalOperationError

    node = getattr(sock, "_node", None)
    node_name = getattr(node, "name", None) or "<unknown-node>"
    socket_name = (
        getattr(sock, "_NAME", None) or getattr(sock, "name", None) or "<socket>"
    )

    common = [
        "General guidance:",
        "  • Wrap logic in a nested @node.graph.",
        "  • Or use the WorkGraph If zone for branching on predicates.",
        "  • Or for loops, use the While zone or Map zone.",
    ]

    msg = (
        f"Illegal operation on a future value (Socket): {what}\n"
        f"Socket: {socket_name} of node '{node_name}'"
    )
    msg += "\n\nFix:\n" + "\n".join(tips + [""] + common)
    raise GraphDeferredIllegalOperationError(msg)


def _tip_cast(kind):  # numeric/bytes/path-like casts
    return [
        f"Avoid {kind} on futures. Compute the value inside the graph, then cast afterwards.",
        "If you need a cast during execution, use a dedicated cast node.",
    ]


def _tip_iter():  # iteration/len/container-ish
    return [
        "You tried to iterate or take len()/index a future.",
        "Use @node.graph to build logic that needs to iterate over values.",
    ]


def _tip_bool():
    return [
        "You used a future in a boolean context (if/while/assert/and/or).",
        "Wrap logic in a nested @node.graph.",
    ]


def _tip_numpy():
    return [
        "NumPy tried to coerce or operate on a future.",
        "Use built-in operator sockets (+, -, *, <, …) to build predicates/expressions,",
        "or use a dedicated numpy/ufunc node.",
    ]


def _tip_ctxmgr():
    return [
        "You tried to use a future as a context manager.",
        "Wrap side effects in a graph node or zone instead.",
    ]


def _tip_indexing():
    return [
        "You tried to subscript a future (obj[idx]).",
        "Index inside the graph (node/zone) where the value is concrete.",
    ]


class OperatorSocketMixin:
    @property
    def _decorator(self):
        from node_graph.decorator import node

        return node

    def _create_operator_node(self, op_func, x, y):
        """Create a "hidden" operator Node in the WorkGraph,
        hooking `self` up as 'x' and `other` as 'y'.
        Return the output socket from that new Node.
        """

        graph = self._node.graph
        if not graph:
            raise ValueError("Socket does not belong to a WorkGraph.")

        new_node = graph.nodes._new(
            self._decorator()(op_func),
            x=x,
            y=y,
        )
        active_zone = getattr(graph, "_active_zone", None)
        if active_zone:
            active_zone.children.add(new_node)
        return new_node.outputs.result

    # Arithmetic Operations
    def __add__(self, other):
        return self._create_operator_node(op_add, self, other)

    def __sub__(self, other):
        return self._create_operator_node(op_sub, self, other)

    def __mul__(self, other):
        return self._create_operator_node(op_mul, self, other)

    def __truediv__(self, other):
        return self._create_operator_node(op_truediv, self, other)

    def __floordiv__(self, other):
        return self._create_operator_node(op_floordiv, self, other)

    def __mod__(self, other):
        return self._create_operator_node(op_mod, self, other)

    def __pow__(self, other):
        return self._create_operator_node(op_pow, self, other)

    # Reverse Arithmetic Operations
    def __radd__(self, other):
        return self._create_operator_node(op_add, other, self)

    def __rsub__(self, other):
        return self._create_operator_node(op_sub, other, self)

    def __rmul__(self, other):
        return self._create_operator_node(op_mul, other, self)

    def __rtruediv__(self, other):
        return self._create_operator_node(op_truediv, other, self)

    def __rfloordiv__(self, other):
        return self._create_operator_node(op_floordiv, other, self)

    def __rmod__(self, other):
        return self._create_operator_node(op_mod, other, self)

    def __rpow__(self, other):
        return self._create_operator_node(op_pow, other, self)

    # Comparison Operations
    def __lt__(self, other):
        return self._create_operator_node(op_lt, self, other)

    def __le__(self, other):
        return self._create_operator_node(op_le, self, other)

    def __gt__(self, other):
        return self._create_operator_node(op_gt, self, other)

    def __ge__(self, other):
        return self._create_operator_node(op_ge, self, other)

    def __eq__(self, other):
        return self._create_operator_node(op_eq, self, other)

    def __ne__(self, other):
        return self._create_operator_node(op_ne, self, other)

    def __rshift__(self, other: BaseSocket | Node | DependencyCollection):
        """
        Called when we do: self >> other
        So we link them or mark that 'other' must wait for 'self'.
        """
        if isinstance(other, DependencyCollection):
            for item in other.items:
                self >> item
        else:
            other._waiting_on.add(self)
        return other

    def __lshift__(self, other: BaseSocket | Node | DependencyCollection):
        """
        Called when we do: self << other
        Means the same as: other >> self
        """
        if isinstance(other, DependencyCollection):
            for item in other.items:
                self << item
        else:
            self._waiting_on.add(other)
        return other

    # Truthiness / boolean contexts
    def __bool__(self):
        _raise_illegal(self, "boolean evaluation", _tip_bool())

    # Numeric casts & indices
    def __int__(self):
        _raise_illegal(self, "int() cast", _tip_cast("int()"))

    def __float__(self):
        _raise_illegal(self, "float() cast", _tip_cast("float()"))

    def __complex__(self):
        _raise_illegal(self, "complex() cast", _tip_cast("complex()"))

    def __index__(self):
        _raise_illegal(self, "use as an index (__index__)", _tip_cast("indexing"))

    def __round__(self, *a, **k):
        _raise_illegal(self, "round()", _tip_cast("round()"))

    def __trunc__(self):
        _raise_illegal(self, "trunc()", _tip_cast("trunc()"))

    def __floor__(self):
        _raise_illegal(self, "math.floor()", _tip_cast("floor()"))

    def __ceil__(self):
        _raise_illegal(self, "math.ceil()", _tip_cast("ceil()"))

    # Sequence / mapping / container protocols
    def __len__(self):
        _raise_illegal(self, "len()", _tip_iter())

    def __iter__(self):
        _raise_illegal(self, "iteration", _tip_iter())

    def __reversed__(self):
        _raise_illegal(self, "reversed()", _tip_iter())

    def __contains__(self, _):
        _raise_illegal(self, "membership test (x in socket)", _tip_iter())

    def __getitem__(self, _):
        _raise_illegal(self, "subscript access (socket[idx])", _tip_indexing())

    def __setitem__(self, *_):
        _raise_illegal(self, "item assignment (socket[idx] = ...)", _tip_indexing())

    def __delitem__(self, *_):
        _raise_illegal(self, "item deletion (del socket[idx])", _tip_indexing())

    # Bitwise / logical operators that people misuse for predicates
    def __and__(self, _):
        _raise_illegal(self, "bitwise and (&) on futures", _tip_bool())

    def __or__(self, _):
        _raise_illegal(self, "bitwise or (|) on futures", _tip_bool())

    def __xor__(self, _):
        _raise_illegal(self, "bitwise xor (^) on futures", _tip_bool())

    def __invert__(self):
        _raise_illegal(self, "bitwise not (~) on futures", _tip_bool())

    def __matmul__(self, _):
        _raise_illegal(self, "matrix multiply (@)", _tip_numpy())

    # Hashing / dict keys / set members
    def __hash__(self):
        _raise_illegal(
            self,
            "hashing (use as dict/set key)",
            ["Futures are not stable keys. Resolve to a concrete value first."],
        )

    # Function-like / context-manager / async
    def __enter__(self):
        _raise_illegal(
            self,
            "context-manager enter (__enter__)",
            ["Use Socket as a context manager is not supported."],
        )

    def __exit__(self, *a):
        _raise_illegal(
            self,
            "context-manager exit (__exit__)",
            ["Use Socket as a context manager is not supported."],
        )

    def __await__(self):
        _raise_illegal(
            self,
            "await on a future (__await__)",
            ["Awaiting is not supported; use @node.graph to build logic instead."],
        )

    def __aiter__(self):
        _raise_illegal(
            self,
            "async iteration (__aiter__)",
            [
                "Async iteration is not supported; use @node.graph to build logic instead."
            ],
        )

    def __anext__(self):
        _raise_illegal(
            self,
            "async next (__anext__)",
            [
                "Async iteration is not supported; use @node.graph to build logic instead."
            ],
        )

    # NumPy interoperability guards
    # Prevent silent coercion to ndarray
    def __array__(self, *a, **k):
        _raise_illegal(self, "NumPy array coercion (__array__)", _tip_numpy())

    # Intercept ufuncs like np.add, np.sin, etc.
    def __array_ufunc__(self, *a, **k):
        _raise_illegal(self, "NumPy ufunc on future (__array_ufunc__)", _tip_numpy())

    # Intercept high-level NumPy functions
    def __array_function__(self, *a, **k):
        _raise_illegal(self, "NumPy high-level op (__array_function__)", _tip_numpy())


class WaitingOn:
    """
    A small helper class that manages 'waiting on' dependencies for a Socket.
    """

    def __init__(self, node: "BaseSocket", graph: "NodeGraph") -> None:
        self.node = node
        self.graph = graph

    def add(self, other: "BaseSocket" | "Node") -> None:
        """Add a socket to the waiting list."""
        from node_graph.node import Node

        if isinstance(other, BaseSocket):
            node = other._node
        elif isinstance(other, Node):
            node = other
        else:
            raise TypeError(f"Expected BaseSocket or Node, got {type(other).__name__}.")
        link_name = f"{node.name}._wait -> {self.node.name}._wait"
        if link_name not in self.graph.links:
            self.graph.add_link(node.outputs._wait, self.node.inputs._wait)
        else:
            print(f"Link {link_name} already exists, skipping creation.")


@dataclass()
class SocketMetadata:
    """A *typed* container for additional socket information.

    Parameters
    ----------
    dynamic
        Whether the socket collection is *dynamic* - i.e. it may grow
        automatically when assigning unknown keys.
    builtin_socket
        Marks sockets that are intrinsic to the framework (e.g. ``_wait`` or
        ``outputs``) so that user code can filter / style them differently.
    extras
        Free form mapping for user extensions.  Any key not matching one of the
        reserved field names ends up in here when converting from an untyped
        ``dict``.
    """

    dynamic: bool = False
    sub_socket_default_link_limit: int = 1
    required: bool = False
    is_metadata: bool = False
    builtin_socket: bool = False
    function_socket: bool = False
    socket_type: str = "INPUT"
    arg_type: str = "kwargs"
    extras: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Return a *plain* dict suitable for JSON serialisation."""

        data = {
            "dynamic": self.dynamic,
            "required": self.required,
            "is_metadata": self.is_metadata,
            "builtin_socket": self.builtin_socket,
            "function_socket": self.function_socket,
            "socket_type": self.socket_type,
            "arg_type": self.arg_type,
        }
        if self.extras:
            # Make sure extras are a dict
            data["extras"] = dict(self.extras)

        # Do not bloat output with empty *extras*
        if not data.get("extras"):
            data.pop("extras", None)
        return data

    @classmethod
    def from_raw(
        cls, raw: Union["SocketMetadata", Dict[str, Any], None]
    ) -> "SocketMetadata":
        """Normalise *raw* user input into a :class:`SocketMetadata` instance."""

        if raw is None:
            return cls()
        if isinstance(raw, cls):
            return raw
        if isinstance(raw, dict):
            # Extract known keys and forward unknown ones into *extras*
            known_keys = {
                "dynamic",
                "builtin_socket",
                "function_socket",
                "socket_type",
                "arg_type",
                "required",
                "is_metadata",
                "sub_socket_default_link_limit",
                "extras",
            }
            known = {k: v for k, v in raw.items() if k in known_keys}
            known.setdefault("extras", {})
            known["extras"].update(
                {k: v for k, v in raw.items() if k not in known_keys}
            )
            return cls(**known)
        raise TypeError(
            f"metadata must be dict | SocketMetadata | None – got {type(raw)!r}"
        )


class TaggedValue(wrapt.ObjectProxy):
    def __init__(self, wrapped, socket=None):
        super().__init__(wrapped)

        self._self_socket = socket

    # Provide clean access via `proxy._socket` instead of `proxy._self_socket`
    @property
    def _socket(self):
        return self._self_socket

    @_socket.setter
    def _socket(self, value):
        self._self_socket = value

    def __copy__(self):
        # shallow-copy the wrapped value, preserve the tag
        from copy import copy as _copy

        w = _copy(self.__wrapped__)
        return type(self)(w, socket=self._socket)

    def __deepcopy__(self, memo):
        from copy import deepcopy as _deepcopy

        # required by wrapt.ObjectProxy
        oid = id(self)
        if oid in memo:
            return memo[oid]
        w = _deepcopy(self.__wrapped__, memo)
        clone = type(self)(w, socket=self._socket)
        memo[oid] = clone
        return clone

    def __reduce_ex__(self, protocol):
        """
        This is the magic method for serialization.

        Instead of returning instructions to rebuild the TaggedValue proxy,
        only the underlying value (self.__wrapped__) gets saved.
        """
        return self.__wrapped__.__reduce_ex__(protocol)


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
        graph: Optional["NodeGraph"] = None,
        link_limit: int = 1,
        metadata: Union[SocketMetadata, Dict[str, Any], None] = None,
        **kwargs: Any,
    ) -> None:
        """Initialize an instance of NodeSocket.

        Args:
            name (str): Name of the socket.
            parent (Optional[Node]): Parent node. Defaults to None.
            type (str, optional): Socket type. Defaults to "INPUT".
            link_limit (int, optional): Maximum number of links. Defaults to 1.
        """
        from node_graph.utils import valid_name_string

        valid_name_string(name)
        self._name = name
        self._node = node
        self._parent = parent
        self._graph = graph
        self._links = []
        self._link_limit = link_limit
        self._metadata: SocketMetadata = SocketMetadata.from_raw(metadata)
        self._waiting_on = WaitingOn(node=self._node, graph=self._graph)

    @property
    def _full_name(self) -> str:
        """Full hierarchical name, including all parent namespaces."""
        if self._parent is not None:
            return f"{self._parent._full_name}.{self._name}"
        return self._name

    @property
    def _scoped_name(self) -> str:
        """The name relative to its immediate parent, excluding the root namespace."""
        return self._full_name.split(".", 1)[-1]

    @property
    def _full_name_with_node(self) -> str:
        """Full hierarchical name, including node name and all parent namespaces."""
        if self._node is not None:
            return f"{self._node.name}.{self._full_name}"
        return self._full_name

    def _to_dict(self) -> Dict[str, Any]:
        """Export the socket to a dictionary for database storage."""
        data: Dict[str, Any] = {
            "name": self._name,
            "identifier": self._identifier,
            "link_limit": self._link_limit,
            "links": [],
            "metadata": self._metadata.to_dict(),
        }
        for link in self._links:
            if self._metadata.socket_type.upper() == "INPUT":
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


class NodeSocket(BaseSocket, OperatorSocketMixin):
    _identifier: str = "NodeSocket"

    _socket_property_class = NodeProperty

    _socket_property_identifier: Optional[str] = None

    def __init__(
        self,
        name: str,
        node: Optional["Node"] = None,
        parent: Optional["NodeSocketNamespace"] = None,
        graph: Optional["NodeGraph"] = None,
        link_limit: int = 1,
        metadata: Optional[dict] = None,
        property: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
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
            graph=graph,
            link_limit=link_limit,
            metadata=metadata,
            **kwargs,
        )
        # Conditionally add a property if property_identifier is provided
        self.property: Optional[NodeProperty] = None
        if self._socket_property_identifier:
            property = property or {}
            property["identifier"] = self._socket_property_identifier
            property["name"] = name
            self.add_property(**(property or {}))

    def add_property(
        self, identifier: str, name: Optional[str] = None, **kwargs: Any
    ) -> None:
        """Add a property to this socket."""
        if name is None:
            name = self._name
        self.property = self._socket_property_class.new(identifier, name=name, **kwargs)

    @property
    def _value(self) -> Any:
        """Get the value of the socket."""
        if self.property:
            return self.property.value
        return None

    @property
    def value(self) -> Any:
        return self._value

    @value.setter
    def value(self, value: Any) -> None:
        self._set_socket_value(value)

    def _set_socket_value(self, value: Any) -> None:
        if isinstance(value, BaseSocket):
            if (
                isinstance(value, NodeSocketNamespace)
                and value._parent is None
                and "_outputs" in value
            ):
                value = value._outputs
            self._node.graph.add_link(value, self)
        elif isinstance(value, TaggedValue):
            self._node.graph.add_link(value._socket, self)
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

    @classmethod
    def _from_dict(cls, data: Dict[str, Any]) -> None:
        # Create a new instance of this class
        socket = cls(
            name=data["name"],
            link_limit=data.get("link_limit", 1),
            metadata=data.get("metadata", {}),
        )
        # Add property
        if data.get("property"):
            socket.add_property(**data["property"])
        return socket

    def _copy(
        self,
        node: Optional["Node"] = None,
        parent: Optional["Node"] = None,
        **kwargs: Any,
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

    if isinstance(identifier, str) and identifier.lower() not in pool:
        items = difflib.get_close_matches(identifier.lower(), pool._keys())
        if len(items) == 0:
            msg = f"Identifier: {identifier} is not defined."
        else:
            msg = f"Identifier: {identifier} is not defined. Did you mean {', '.join(item.lower() for item in items)}?"
        raise ValueError(msg)


def _raise_namespace_assignment_error(
    *,
    target_ns: "NodeSocketNamespace",
    incoming_desc: str,
    reason: str,
    fixes: list[str],
) -> None:
    """Raise a ValueError guiding users when setting/linking values into a namespace."""
    where = getattr(target_ns, "_full_name_with_node", "<namespace>")
    msg = [
        f"Invalid assignment into namespace socket: {where}",
        "",
        "What happened:",
        f"  • {reason}",
        f"  • Incoming value: {incoming_desc}",
        "",
        "Why this matters:",
        "  • Without a namespace-typed graph input, the whole dict is treated as *one value*,",
        "    so its inner keys are NOT wired to the child sockets. You'd end up with missing links.",
        "",
        "How to fix:",
        *[f"  • {line}" for line in fixes],
    ]
    raise ValueError("\n".join(msg))


class NodeSocketNamespace(BaseSocket, OperatorSocketMixin):
    """A NodeSocket that also acts as a namespace (collection) of other sockets."""

    _identifier: str = "node_graph.namespace"
    _type_mapping: dict = type_mapping

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
        link_limit: int = 1000000,
        metadata: Union[SocketMetadata, Dict[str, Any], None] = None,
        sockets: Optional[Dict[str, object]] = None,
        pool: Optional[object] = None,
        entry_point: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        # Initialize NodeSocket first
        BaseSocket.__init__(
            self,
            name=name,
            node=node,
            parent=parent,
            link_limit=link_limit,
            metadata=metadata,
            **kwargs,
        )
        #
        self._sockets: Dict[str, object] = {}
        self._parent = parent
        self._SocketPool = None
        # one can specify the pool or entry_point to get the pool
        if pool is not None:
            self._SocketPool = pool
        elif entry_point is not None and self._SocketPool is None:
            self._SocketPool = EntryPointPool(entry_point_group=entry_point)
        else:
            from node_graph.sockets import SocketPool

            self._SocketPool = SocketPool

        if self._metadata.dynamic:
            self._link_limit = 1000000
        if sockets is not None:
            for key, socket in sockets.items():
                kwargs = {}
                if "property" in socket:
                    kwargs["property"] = socket["property"]
                if "sockets" in socket:
                    kwargs["sockets"] = socket["sockets"]
                self._new(
                    socket["identifier"],
                    name=key,
                    metadata=socket.get("metadata", {}),
                    **kwargs,
                )

    def __getattr__(self, name: str) -> Any:
        """
        We check if it is in our _sockets. If so, return that sub-socket.
        Otherwise, raise AttributeError.
        """
        # By explicitly raising an AttributeError, Python will continue its normal flow
        # We still hardcoded the built-in sockets: _wait and outputs
        if name.startswith("_") and name not in ["_wait", "_outputs"]:
            raise AttributeError(f"{self.__class__.__name__} has no attribute '{name}'")
        try:
            return self._sockets[name]
        except KeyError:
            avail = ", ".join(self._sockets.keys()) or "<none>"
            raise AttributeError(
                f"{self.__class__.__name__}: '{self._full_name_with_node}' has no sub-socket '{name}'.\n"
                f"Available: {avail}\n"
                f"Tip: If '{name}' should exist, add it to the SocketSpec (or make this namespace dynamic)."
            )

    def __setattr__(self, name: str, value: Any) -> None:
        """
        Override __setattr__ so that doing `namespace_socket.some_name = x`
        either sets the property or links to another socket, rather than
        replacing the entire sub-socket object.
        """
        # If the attribute name is "private" or reserved, do normal attribute setting
        if name.startswith("_"):
            object.__setattr__(self, name, value)
            return

        self._set_socket_value(
            {name: value}, link_limit=self._metadata.sub_socket_default_link_limit
        )

    def __setitem__(self, key: str | int, value: Any) -> None:
        """
        Override __setitem__ so that doing `namespace_socket[key] = x`
        either sets the property or links to another socket, rather than
        replacing the entire sub-socket object.
        """
        if isinstance(key, int):
            key = list(self._sockets.keys())[key]
        self.__setattr__(key, value)

    def __dir__(self) -> list[str]:
        """
        Make tab-completion more friendly:
        """
        # Get the list of default attributes from the parent class
        default_attrs = super().__dir__()

        # Get the custom attributes from the _sockets dictionary
        socket_attrs = self._sockets.keys()

        # Combine the default and custom attributes, remove duplicates, and sort
        return sorted(list(set(default_attrs) | set(socket_attrs)))

    def _new(
        self,
        identifier: Union[str, type] = None,
        name: Optional[str] = None,
        metadata: Optional[dict] = None,
        **kwargs: Any,
    ) -> object:
        identifier = identifier or self._SocketPool["any"]
        check_identifier_name(identifier, self._SocketPool)

        _names = name.split(".", 1)
        if len(_names) > 1:
            namespace = _names[0]
            if namespace not in self:
                # if the namespace is dynamic, create sub-sockets if it does not exist
                if self._metadata.dynamic:
                    # the sub-socket should also be dynamic
                    self._new(
                        self._SocketPool["namespace"],
                        namespace,
                        metadata={
                            "dynamic": True,
                            "sub_socket_default_link_limit": self._metadata.sub_socket_default_link_limit,
                        },
                    )
                else:
                    raise ValueError(
                        f"Namespace {namespace} does not exist in the socket collection."
                    )
            return self[namespace]._new(
                identifier,
                _names[1],
                link_limit=self._metadata.sub_socket_default_link_limit,
                metadata=metadata,
            )
        else:
            ItemClass = get_item_class(identifier, self._SocketPool)
            kwargs.pop("graph", None)
            kwargs.setdefault(
                "link_limit", self._metadata.sub_socket_default_link_limit
            )
            item = ItemClass(
                name,
                node=self._node,
                parent=self,
                graph=self._graph,
                metadata=metadata,
                pool=self._SocketPool,
                **kwargs,
            )
            self._append(item)
            return item

    @property
    def _value(self) -> Dict[str, Any]:
        return self._collect_values()

    def _collect_values(self, raw: bool = True) -> Dict[str, Any]:
        data = {}
        for name, item in self._sockets.items():
            if isinstance(item, NodeSocketNamespace):
                value = item._collect_values(raw=raw)
                if value:
                    data[name] = value
            else:
                if item.value is not None:
                    if raw:
                        data[name] = (
                            item.value.__wrapped__
                            if isinstance(item.value, TaggedValue)
                            else item.value
                        )
                    else:
                        data[name] = item.value
        return data

    @_value.setter
    def _value(self, value: Dict[str, Any]) -> None:
        self._set_socket_value(value)

    def _set_socket_value(self, value: Dict[str, Any] | NodeSocket, **kwargs) -> None:
        """Set value(s) into this namespace.

        Supports:
        - linking another socket (BaseSocket)
        - nested dicts
        - dotted keys like "data.x" or "nested.data.x"

        Creation rules:
        - Missing immediate children can be created only if *this* namespace is dynamic.
        - Intermediate dotted segments are created as namespaces (dynamic=True) when needed.
        """
        if value is None:
            return

        # Link another socket directly to this namespace
        if isinstance(value, BaseSocket):
            self._node.graph.add_link(value, self)
            return

        if isinstance(value, TaggedValue):
            src = getattr(
                getattr(value, "_socket", None),
                "_full_name_with_node",
                "<unknown-socket>",
            )
            _raise_namespace_assignment_error(
                target_ns=self,
                incoming_desc=f"TaggedValue(dict) from {src}",
                reason="A TaggedValue wrapping a dict is being assigned to a *namespace*.",
                fixes=[
                    "Annotate the graph-level parameter as a namespace, e.g.:",
                    f"    def your_graph({self._name}: Annotated[dict, namespace({list(self._sockets.keys())[0]}=, ...)]):",
                    "",
                    "Or reuse the node’s own input spec, e.g.:",
                    f"    def your_graph({self._name}: Annotated[dict, add_multiply.inputs.data]):",
                    "        add_multiply(data=data)",
                    "",
                ],
            )

        if not isinstance(value, dict):
            _raise_namespace_assignment_error(
                target_ns=self,
                incoming_desc=type(value).__name__,
                reason="This is a namespace socket and expects a dict (or a Socket link).",
                fixes=[
                    "Provide a dict with keys matching the namespace fields;",
                    "or link another socket/namespace; or declare the graph input as a namespace.",
                ],
            )

        for key, val in value.items():
            # If the key is dotted, descend or create per segment
            if "." in key:
                head, tail = key.split(".", 1)

                # Ensure the immediate child exists (create if allowed)
                if head not in self._sockets:
                    if not self._metadata.dynamic:
                        _raise_namespace_assignment_error(
                            target_ns=self,
                            incoming_desc=f"key '{head}'",
                            reason=f"Field '{head}' is not defined and this namespace is not dynamic.",
                            fixes=[
                                "Define the field in the socket spec (preferred); or",
                                "mark this namespace dynamic if it must accept arbitrary keys;",
                                "or correct the key path being assigned.",
                            ],
                        )
                    # We are going to descend (tail exists), so create a namespace
                    self._new(
                        self._SocketPool["namespace"],
                        head,
                        metadata={
                            "dynamic": True,
                            "sub_socket_default_link_limit": self._metadata.sub_socket_default_link_limit,
                        },
                        **kwargs,
                    )

                child = self._sockets[head]
                if not isinstance(child, NodeSocketNamespace):
                    _raise_namespace_assignment_error(
                        target_ns=self,
                        incoming_desc=f"nested key '{key}' under leaf '{head}'",
                        reason=f"'{head}' is a leaf socket, but you attempted to assign nested data below it.",
                        fixes=[
                            "Use a namespace socket for hierarchical data; update your SocketSpec accordingly; or",
                            "flatten your assignment to target a leaf socket directly.",
                        ],
                    )

                # Recurse into the child namespace with the remaining tail
                child._set_socket_value({tail: val}, **kwargs)
                continue  # next key

            # Non-dotted key path (single-segment)
            if key not in self._sockets:
                if not self._metadata.dynamic:
                    _raise_namespace_assignment_error(
                        target_ns=self,
                        incoming_desc=f"key '{key}'",
                        reason=f"Field '{key}' is not defined and this namespace is not dynamic.",
                        fixes=[
                            "Add the field to the namespace spec; or",
                            "make the namespace dynamic if it should grow automatically.",
                        ],
                    )

                # Decide whether to create a namespace or a leaf based on the value type
                if isinstance(val, (dict, NodeSocketNamespace)):
                    # create child namespace (dynamic)
                    self._new(
                        self._SocketPool["namespace"],
                        key,
                        metadata={
                            "dynamic": True,
                            "sub_socket_default_link_limit": self._metadata.sub_socket_default_link_limit,
                        },
                        **kwargs,
                    )
                else:
                    # create a leaf socket that can accept "any"
                    self._new(self._SocketPool["any"], key, **kwargs)

            # Now we’re guaranteed the key exists; delegate appropriately
            target = self._sockets[key]
            if isinstance(target, NodeSocketNamespace):
                # If incoming val is a dict, recurse. If it’s a socket, link to the namespace.
                if isinstance(val, dict):
                    target._set_socket_value(val, **kwargs)
                elif isinstance(val, BaseSocket):
                    self._node.graph.add_link(val, target)
                else:
                    # Treat setting a leaf value into a namespace as error for clarity
                    _raise_namespace_assignment_error(
                        target_ns=target,
                        incoming_desc=type(val).__name__,
                        reason="A namespace expects a mapping of fields, but a non-dict value was provided.",
                        fixes=[
                            "Provide a dict like {'x': 1, 'y': 2} that matches the namespace shape.",
                        ],
                    )
            else:
                # Leaf socket: forward to its own setter (which handles linking or value assignment)
                target._set_socket_value(val)

    @property
    def _all_links(self) -> List["NodeLink"]:
        links = []
        for item in self._sockets.values():
            links.extend(item._links)
            if isinstance(item, NodeSocketNamespace):
                links.extend(item._all_links)
        return links

    def _to_dict(self) -> Dict[str, Any]:
        data = super()._to_dict()
        data["sockets"] = {}
        # Add nested sockets information
        for item in self._sockets.values():
            data["sockets"][item._name] = item._to_dict()
        return data

    @classmethod
    def _from_dict(
        cls,
        data: Dict[str, Any],
        node: Optional["Node"] = None,
        parent: Optional["NodeSocket"] = None,
        pool: Optional[object] = None,
        **kwargs: Any,
    ) -> None:
        # Create a new instance of this class
        ns = cls(
            name=data["name"],
            link_limit=data.get("link_limit", 1),
            metadata=data.get("metadata", {}),
            node=node,
            parent=parent,
            graph=kwargs.pop("graph", None),
            pool=pool,
            **kwargs,
        )
        # Add nested sockets
        for name, item_data in data.get("sockets", {}).items():
            item_data["name"] = name
            ns._new(**item_data)
        return ns

    @classmethod
    def _from_spec(
        cls,
        name: str,
        spec: "SocketSpec",
        *,
        node: Optional["Node"],
        graph: Optional["NodeGraph"],
        parent: Optional["NodeSocket"] = None,
        pool: Optional[object] = None,
        role: str = "input",
    ) -> "NodeSocketNamespace":
        """
        Materialize a runtime namespace (and children) from a SocketSpec.
        The *spec* must be a namespace.
        """
        from node_graph.materialize import runtime_meta_from_spec

        if spec.identifier != cls._type_mapping["namespace"]:
            raise ValueError(
                f"The socket spec identifier must be a namespace, got: {spec.identifier}"
            )

        ns_meta = runtime_meta_from_spec(
            spec, role=role, function_generated=True, type_mapping=cls._type_mapping
        )
        ns = cls(
            name=name,
            node=node,
            parent=parent,
            graph=graph,
            metadata=ns_meta,
            pool=pool or (node.SocketPool if node else None),
        )

        # materialize fixed fields
        for fname, f_spec in (spec.fields or {}).items():
            cls._append_from_spec(ns, fname, f_spec, node=node, graph=graph, role=role)
        return ns

    @classmethod
    def _append_from_spec(
        cls,
        parent_ns: "NodeSocketNamespace",
        name: str,
        spec: "SocketSpec",
        *,
        node,
        graph,
        role: str,
    ) -> None:
        from copy import deepcopy
        from node_graph.materialize import runtime_meta_from_spec

        if spec.identifier == cls._type_mapping["namespace"]:
            child_meta = runtime_meta_from_spec(
                spec, role=role, function_generated=True, type_mapping=cls._type_mapping
            )
            child = cls(
                name=name,
                node=node,
                parent=parent_ns,
                graph=graph,
                metadata=child_meta,
                pool=parent_ns._SocketPool,
            )
            parent_ns._append(child)

            for fname, f_spec in (spec.fields or {}).items():
                cls._append_from_spec(
                    child,
                    fname,
                    f_spec,
                    node=node,
                    graph=graph,
                    role=role,
                )
        else:
            # leaf
            leaf_meta = runtime_meta_from_spec(
                spec, role=role, function_generated=True, type_mapping=cls._type_mapping
            )

            prop = {"identifier": spec.identifier}
            if not isinstance(spec.default, type(MISSING)):
                prop["default"] = deepcopy(spec.default)

            ItemClass = get_item_class(spec.identifier, parent_ns._SocketPool)
            sock = ItemClass(
                name=name,
                node=node,
                parent=parent_ns,
                graph=graph,
                metadata=leaf_meta,
                property=prop,
                link_limit=parent_ns._metadata.sub_socket_default_link_limit,
            )
            parent_ns._append(sock)

    def _copy(
        self,
        node: Optional[Node] = None,
        parent: Optional[NodeSocket] = None,
        skip_linked: bool = False,
        skip_builtin: bool = False,
    ) -> "NodeSocketNamespace":
        # Copy as parentSocket
        parent = self._parent if parent is None else parent
        ns_copy = self.__class__(
            self._name,
            node=node,
            parent=parent,
            link_limit=self._link_limit,
            metadata=self._metadata,
        )
        # Copy nested sockets
        for item in self._sockets.values():
            if len(item._links) > 0 and skip_linked:
                continue
            if skip_builtin and item._name in ["_wait", "_outputs"]:
                continue
            ns_copy._append(
                item._copy(node=node, parent=ns_copy, skip_linked=skip_linked)
            )
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
                f""""{key}" is not in this namespace: {self._full_name_with_node}. Acceptable names are {self._get_keys()}."""
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
                child = self._sockets[keys[0]]
                if isinstance(child, NodeSocketNamespace):
                    return keys[1] in child
                return False  # cannot have nested under a non-namespace
            return True
        return False

    def _append(self, item: object) -> None:
        """Append item into this collection."""
        if item._name in self._sockets:
            raise ValueError(f"Name '{item._name}' already exists in the namespace.")
        if item._name.upper() in self._RESERVED_NAMES:
            raise ValueError(f"Name '{item._name}' is reserved by the namespace.")
        self._sockets[item._name] = item

    def _get(self, name: str) -> object:
        """Find item by name

        Args:
            name (str): _description_

        Returns:
            object: _description_
        """

    def _get_all_keys(self) -> List[str]:
        # keys in the collection, with the option to include nested keys
        keys = [item._scoped_name for item in self._sockets.values()]
        for item in self._sockets.values():
            if isinstance(item, NodeSocketNamespace):
                keys.extend(item._get_all_keys())
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
        return f"{self.__class__.__name__}(name='{self._name}', sockets={nested})"
