from node_graph.socket import NodeSocket
from node_graph.serializer import SerializeJson, SerializePickle


class SocketGeneral(NodeSocket, SerializePickle):
    """General socket."""

    identifier: str = "General"

    def __init__(
        self, name, node=None, type="INPUT", index=0, uuid=None, **kwargs
    ) -> None:
        super().__init__(name, node, type, index, uuid=uuid)
        self.add_property("General", name, **kwargs)


class SocketFloat(NodeSocket, SerializeJson):
    """Float socket."""

    identifier: str = "Float"

    def __init__(
        self, name, node=None, type="INPUT", index=0, uuid=None, **kwargs
    ) -> None:
        super().__init__(name, node, type, index, uuid=uuid)
        self.add_property("Float", name, **kwargs)


class SocketInt(NodeSocket, SerializeJson):
    """Int socket."""

    identifier: str = "Int"

    def __init__(
        self, name, node=None, type="INPUT", index=0, uuid=None, **kwargs
    ) -> None:
        super().__init__(name, node, type, index, uuid=uuid)
        self.add_property("Int", name, **kwargs)


class SocketString(NodeSocket, SerializeJson):
    """String socket."""

    identifier: str = "String"

    def __init__(
        self, name, node=None, type="INPUT", index=0, uuid=None, **kwargs
    ) -> None:
        super().__init__(name, node, type, index, uuid=uuid)
        self.add_property("String", name, **kwargs)


class SocketBool(NodeSocket, SerializeJson):
    """Bool socket."""

    identifier: str = "Bool"

    def __init__(
        self, name, node=None, type="INPUT", index=0, uuid=None, **kwargs
    ) -> None:
        super().__init__(name, node, type, index, uuid=uuid)
        self.add_property("Bool", name, **kwargs)


class SocketBaseList(NodeSocket, SerializeJson):
    """Socket with a BaseList property."""

    identifier: str = "BaseList"

    def __init__(
        self, name, node=None, type="INPUT", index=0, uuid=None, **kwargs
    ) -> None:
        super().__init__(name, node, type, index, uuid=uuid)
        self.add_property("BaseList", name, **kwargs)


class SocketBaseDict(NodeSocket, SerializeJson):
    """Socket with a BaseDict property."""

    identifier: str = "BaseDict"

    def __init__(
        self, name, node=None, type="INPUT", index=0, uuid=None, **kwargs
    ) -> None:
        super().__init__(name, node, type, index, uuid=uuid)
        self.add_property("BaseDict", name, **kwargs)


class SocketIntVector(NodeSocket, SerializeJson):
    """Socket with a IntVector property."""

    identifier: str = "IntVector"

    def __init__(
        self, name, node=None, type="INPUT", index=0, uuid=None, **kwargs
    ) -> None:
        super().__init__(name, node, type, index, uuid=uuid)
        self.add_property("IntVector", name, **kwargs)


class SocketFloatVector(NodeSocket, SerializeJson):
    """Socket with a FloatVector property."""

    identifier: str = "FloatVector"

    def __init__(
        self, name, node=None, type="INPUT", index=0, uuid=None, **kwargs
    ) -> None:
        super().__init__(name, node, type, index, uuid=uuid)
        self.add_property("FloatVector", name, **kwargs)


socket_list = [
    SocketGeneral,
    SocketInt,
    SocketFloat,
    SocketString,
    SocketBool,
    SocketBaseDict,
    SocketBaseList,
    SocketIntVector,
    SocketFloatVector,
]
