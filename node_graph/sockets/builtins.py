from node_graph.socket import NodeSocket
from node_graph.serializer import SerializeJson, SerializePickle


class SocketAny(NodeSocket, SerializePickle):
    """Any socket."""

    identifier: str = "node_graph.any"

    def __init__(
        self, name, node=None, type="INPUT", index=0, uuid=None, **kwargs
    ) -> None:
        super().__init__(name, node, type, index, uuid=uuid)
        self.add_property("node_graph.any", name, **kwargs)


class SocketFloat(NodeSocket, SerializeJson):
    """Float socket."""

    identifier: str = "node_graph.float"

    def __init__(
        self, name, node=None, type="INPUT", index=0, uuid=None, **kwargs
    ) -> None:
        super().__init__(name, node, type, index, uuid=uuid)
        self.add_property("node_graph.float", name, **kwargs)


class SocketInt(NodeSocket, SerializeJson):
    """Int socket."""

    identifier: str = "node_graph.int"

    def __init__(
        self, name, node=None, type="INPUT", index=0, uuid=None, **kwargs
    ) -> None:
        super().__init__(name, node, type, index, uuid=uuid)
        self.add_property("node_graph.int", name, **kwargs)


class SocketString(NodeSocket, SerializeJson):
    """String socket."""

    identifier: str = "node_graph.string"

    def __init__(
        self, name, node=None, type="INPUT", index=0, uuid=None, **kwargs
    ) -> None:
        super().__init__(name, node, type, index, uuid=uuid)
        self.add_property("node_graph.string", name, **kwargs)


class SocketBool(NodeSocket, SerializeJson):
    """Bool socket."""

    identifier: str = "node_graph.bool"

    def __init__(
        self, name, node=None, type="INPUT", index=0, uuid=None, **kwargs
    ) -> None:
        super().__init__(name, node, type, index, uuid=uuid)
        self.add_property("node_graph.bool", name, **kwargs)


class SocketBaseList(NodeSocket, SerializeJson):
    """Socket with a BaseList property."""

    identifier: str = "node_graph.base_list"

    def __init__(
        self, name, node=None, type="INPUT", index=0, uuid=None, **kwargs
    ) -> None:
        super().__init__(name, node, type, index, uuid=uuid)
        self.add_property("node_graph.base_list", name, **kwargs)


class SocketBaseDict(NodeSocket, SerializeJson):
    """Socket with a BaseDict property."""

    identifier: str = "node_graph.base_dict"

    def __init__(
        self, name, node=None, type="INPUT", index=0, uuid=None, **kwargs
    ) -> None:
        super().__init__(name, node, type, index, uuid=uuid)
        self.add_property("node_graph.base_dict", name, **kwargs)


class SocketIntVector(NodeSocket, SerializeJson):
    """Socket with a IntVector property."""

    identifier: str = "node_graph.int_vector"

    def __init__(
        self, name, node=None, type="INPUT", index=0, uuid=None, **kwargs
    ) -> None:
        super().__init__(name, node, type, index, uuid=uuid)
        self.add_property("node_graph.int_vector", name, **kwargs)


class SocketFloatVector(NodeSocket, SerializeJson):
    """Socket with a FloatVector property."""

    identifier: str = "node_graph.float_vector"

    def __init__(
        self, name, node=None, type="INPUT", index=0, uuid=None, **kwargs
    ) -> None:
        super().__init__(name, node, type, index, uuid=uuid)
        self.add_property("node_graph.float_vector", name, **kwargs)
