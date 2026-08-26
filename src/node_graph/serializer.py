from typing import Any


class SerializationAdapter:
    id: str = "null"
    name: str = "null"

    def validate(self, value: Any, socket: Any, *, mode: str = "assign") -> Any:
        return value

    def serialize(self, value: Any, socket: Any, *, store: bool) -> Any:
        return value

    def deserialize(self, value: Any, socket: Any) -> Any:
        return value

    def to_python(self, value: Any) -> Any:
        """Return ``value`` as the plain Python a contract can be checked against.

        A graph body is handed whatever the engine wraps its values in, which
        is right for drawing links and wrong for validating: a model declaring
        ``str`` cannot be asked to accept a storage node holding one. An
        adapter that wraps values answers this with what they hold.
        """
        return value

    def serialize_ports(
        self, python_data: Any, port_schema: Any, *, store: bool
    ) -> Any:
        return python_data


class NullSerializationAdapter(SerializationAdapter):
    id: str = "null"
    name: str = "null"
