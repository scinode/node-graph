from node_graph.socket import TaskSocket
from node_graph.serializer import SerializeJson


class SocketAny(TaskSocket, SerializeJson):
    """Socket that accepts any type of data."""

    _identifier: str = "node_graph.any"
    _socket_property_identifier: str = "node_graph.any"


class SocketNamespace(TaskSocket, SerializeJson):
    """Socket that holds a namespace."""

    _identifier: str = "node_graph.namespace"
    _socket_property_identifier: str = "node_graph.any"


class SocketFloat(TaskSocket, SerializeJson):
    """Socket for float data."""

    _identifier: str = "node_graph.float"
    _socket_property_identifier: str = "node_graph.float"


class SocketInt(TaskSocket, SerializeJson):
    """Socket for integer data."""

    _identifier: str = "node_graph.int"
    _socket_property_identifier: str = "node_graph.int"


class SocketString(TaskSocket, SerializeJson):
    """Socket for string data."""

    _identifier: str = "node_graph.string"
    _socket_property_identifier: str = "node_graph.string"


class SocketBool(TaskSocket, SerializeJson):
    """Socket for boolean data."""

    _identifier: str = "node_graph.bool"
    _socket_property_identifier: str = "node_graph.bool"


class SocketBaseList(TaskSocket, SerializeJson):
    """Socket with a BaseList property."""

    _identifier: str = "node_graph.base_list"
    _socket_property_identifier: str = "node_graph.base_list"


class SocketBaseDict(TaskSocket, SerializeJson):
    """Socket with a BaseDict property."""

    _identifier: str = "node_graph.base_dict"
    _socket_property_identifier: str = "node_graph.base_dict"


class SocketIntVector(TaskSocket, SerializeJson):
    """Socket for integer vector data."""

    _identifier: str = "node_graph.int_vector"
    _socket_property_identifier: str = "node_graph.int_vector"


class SocketFloatVector(TaskSocket, SerializeJson):
    """Socket for float vector data."""

    _identifier: str = "node_graph.float_vector"
    _socket_property_identifier: str = "node_graph.float_vector"
