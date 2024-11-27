from node_graph.socket import NodeSocket
from node_graph.serializer import SerializeJson, SerializePickle


class SocketAny(NodeSocket, SerializePickle):
    """Socket that accepts any type of data."""

    identifier: str = "node_graph.any"
    property_identifier: str = "node_graph.any"


class SocketNamespace(NodeSocket, SerializePickle):
    """Socket that holds a namespace."""

    identifier: str = "node_graph.namespace"
    property_identifier: str = "node_graph.any"


class SocketFloat(NodeSocket, SerializeJson):
    """Socket for float data."""

    identifier: str = "node_graph.float"
    property_identifier: str = "node_graph.float"


class SocketInt(NodeSocket, SerializeJson):
    """Socket for integer data."""

    identifier: str = "node_graph.int"
    property_identifier: str = "node_graph.int"


class SocketString(NodeSocket, SerializeJson):
    """Socket for string data."""

    identifier: str = "node_graph.string"
    property_identifier: str = "node_graph.string"


class SocketBool(NodeSocket, SerializeJson):
    """Socket for boolean data."""

    identifier: str = "node_graph.bool"
    property_identifier: str = "node_graph.bool"


class SocketBaseList(NodeSocket, SerializeJson):
    """Socket with a BaseList property."""

    identifier: str = "node_graph.base_list"
    property_identifier: str = "node_graph.base_list"


class SocketBaseDict(NodeSocket, SerializeJson):
    """Socket with a BaseDict property."""

    identifier: str = "node_graph.base_dict"
    property_identifier: str = "node_graph.base_dict"


class SocketIntVector(NodeSocket, SerializeJson):
    """Socket for integer vector data."""

    identifier: str = "node_graph.int_vector"
    property_identifier: str = "node_graph.int_vector"


class SocketFloatVector(NodeSocket, SerializeJson):
    """Socket for float vector data."""

    identifier: str = "node_graph.float_vector"
    property_identifier: str = "node_graph.float_vector"
