from node_graph.socket import NodeSocket
from node_graph.serializer import SerializeJson, SerializePickle


class SocketAny(NodeSocket, SerializePickle):
    """Socket that accepts any type of data."""

    _identifier: str = "node_graph.any"
    _socket_property_identifier: str = "node_graph.any"


class SocketNamespace(NodeSocket, SerializePickle):
    """Socket that holds a namespace."""

    _identifier: str = "node_graph.namespace"
    _socket_property_identifier: str = "node_graph.any"


class SocketFloat(NodeSocket, SerializeJson):
    """Socket for float data."""

    _identifier: str = "node_graph.float"
    _socket_property_identifier: str = "node_graph.float"


class SocketInt(NodeSocket, SerializeJson):
    """Socket for integer data."""

    _identifier: str = "node_graph.int"
    _socket_property_identifier: str = "node_graph.int"


class SocketString(NodeSocket, SerializeJson):
    """Socket for string data."""

    _identifier: str = "node_graph.string"
    _socket_property_identifier: str = "node_graph.string"


class SocketBool(NodeSocket, SerializeJson):
    """Socket for boolean data."""

    _identifier: str = "node_graph.bool"
    _socket_property_identifier: str = "node_graph.bool"


class SocketBaseList(NodeSocket, SerializeJson):
    """Socket with a BaseList property."""

    _identifier: str = "node_graph.base_list"
    _socket_property_identifier: str = "node_graph.base_list"


class SocketBaseDict(NodeSocket, SerializeJson):
    """Socket with a BaseDict property."""

    _identifier: str = "node_graph.base_dict"
    _socket_property_identifier: str = "node_graph.base_dict"


class SocketIntVector(NodeSocket, SerializeJson):
    """Socket for integer vector data."""

    _identifier: str = "node_graph.int_vector"
    _socket_property_identifier: str = "node_graph.int_vector"


class SocketFloatVector(NodeSocket, SerializeJson):
    """Socket for float vector data."""

    _identifier: str = "node_graph.float_vector"
    _socket_property_identifier: str = "node_graph.float_vector"
