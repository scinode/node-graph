from typing import Optional, Callable, Dict, Any, Union


class NodeProperty:
    """Base class for Node properties.

    A property holds data that can be displayed or modified in a GUI, with an optional update callback.
    """

    property_entry: str = "node_graph.property"
    identifier: str = "NodeProperty"
    allowed_types = (object,)  # Allow any type

    def __init__(
        self,
        name: str,
        description: str = "",
        default: Any = None,
        update: Optional[Callable[[], None]] = None,
        arg_type: Optional[str] = "kwargs",
        value: Any = None,
        **kwargs,
    ) -> None:
        """
        Initialize a NodeProperty.

        Args:
            name (str): The name of the property.
            description (str, optional): A description of the property. Defaults to "".
            default (Any, optional): The default value of the property. Defaults to None.
            update (Callable[[], None], optional): Callback to invoke when the value changes. Defaults to None.
        """
        self.name = name
        self.description = description
        self.default = default
        self.update = update
        self.arg_type = arg_type
        self._value = default
        if value is not None:
            self.value = value

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the property to a dictionary for database storage."""
        data = {
            "value": self.value,
            "name": self.name,
            "identifier": self.identifier,
            "default": self.default,
            "metadata": self.get_metadata(),
            "arg_type": self.arg_type,
        }
        # Conditionally add serializer/deserializer if they are defined
        if hasattr(self, "get_serialize") and callable(self.get_serialize):
            data["serialize"] = self.get_serialize()

        if hasattr(self, "get_deserialize") and callable(self.get_deserialize):
            data["deserialize"] = self.get_deserialize()

        return data

    def get_metadata(self) -> Dict[str, Any]:
        """Return metadata related to this property."""
        return {}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NodeProperty":
        """Create a NodeProperty from a serialized dictionary."""
        prop = cls(
            name=data["name"],
            description=data.get("description", ""),
            default=data.get("default"),
        )
        prop.identifier = data["identifier"]
        prop.value = data["value"]
        return prop

    def update_from_dict(self, data: Dict[str, Any]) -> None:
        """Update the property from a dictionary."""
        self.value = data["value"]

    @property
    def value(self) -> Any:
        return self._value

    @value.setter
    def value(self, value: Any) -> None:
        self.set_value(value)

    def set_value(self, value: Any) -> None:
        """Set the value and invoke the update callback if present."""
        self.validate(value)
        self._value = value
        if self.update:
            self.update()

    def validate(self, value: Any) -> None:
        """Validate the given value based on allowed types."""
        if not isinstance(value, self.allowed_types):
            raise TypeError(
                f"Expected value of type {self.allowed_types}, got {type(value).__name__} instead."
            )

    def copy(self) -> "NodeProperty":
        """Create a shallow copy of the property."""
        return self.__class__(
            name=self.name,
            description=self.description,
            default=self._value,
            update=self.update,
        )

    @classmethod
    def new(
        cls,
        identifier: Union[str, type],
        name: str = None,
        PropertyPool: Dict[str, "NodeProperty"] = None,
        **kwargs,
    ) -> "NodeProperty":
        """Create a new property from an identifier."""
        from node_graph.collection import get_item_class

        if PropertyPool is None:
            from node_graph.properties import PropertyPool

        ItemClass = get_item_class(identifier, PropertyPool, NodeProperty)
        return ItemClass(name=name, **kwargs)

    def __str__(self) -> str:
        return f'{self.__class__.__name__}(name="{self.name}", value={self._value})'

    def __repr__(self) -> str:
        return self.__str__()
