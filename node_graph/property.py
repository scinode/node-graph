from typing import Callable, Dict, Any, Union


class NodeProperty:
    """Base class for Node properties.

    A property holds data that can be shown or modified in a GUI, with an optional update callback.
    """

    property_entry: str = "node_graph.property"
    identifier: str = "NodeProperty"
    allowed_types = (object,)  # Allow any type

    def __init__(
        self,
        name: str,
        description: str = "",
        default: Any = None,
        update: Callable[[], None] = None,
    ) -> None:
        """
        Initialize a NodeProperty.

        Args:
            name (str): The name of the property.
            description (str, optional): A description of the property. Defaults to "".
            default (Any, optional): The default value of the property. Defaults to None.
            update (Callable[[], None], optional): Callback to invoke when the value changes. Defaults to None.
        """
        self.name: str = name
        self.description: str = description
        self.default: Any = default
        self.update: Callable[[], None] = update
        self._value = self.default

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the property to a dictionary for database storage."""
        return {
            "value": self.value,
            "name": self.name,
            "identifier": self.identifier,
            "serialize": self.get_serialize(),
            "deserialize": self.get_deserialize(),
            "metadata": self.get_metadata(),
        }

    def get_metadata(self) -> Dict[str, Any]:
        """Return metadata related to this property."""
        return {"default": self.default}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NodeProperty":
        """Create a NodeProperty from a serialized dictionary."""
        prop = cls(data["name"])
        prop.identifier = data["identifier"]
        prop.value = data["value"]
        return prop

    def update_from_dict(self, data: Dict[str, Any]) -> None:
        """Update the value of the property from a dictionary."""
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

    def validate(self, value: any) -> None:
        """Validate the given value based on allowed types."""
        if not isinstance(value, self.allowed_types):
            raise TypeError(
                f"Expected value of type {self.allowed_types}, got {type(value).__name__} instead."
            )

    def copy(self) -> "NodeProperty":
        """Create a shallow copy of the property.

        Note: Callback functions are not copied.
        """
        return self.__class__(self.name, self.description, self.value, self.update)

    @classmethod
    def new(
        cls,
        identifier: Union[str, type],
        name: str = None,
        data: Dict[str, Any] = {},
        property_pool: Dict[str, "NodeProperty"] = None,
    ) -> "NodeProperty":
        """Create a new property from an identifier.

        Args:
            identifier (Union[str, type]): The identifier for the property class.
            name (str, optional): The name of the property. Defaults to None.
            data (Dict[str, Any], optional): Additional data for property initialization. Defaults to {}.
            property_pool (Dict[str, NodeProperty], optional): A pool of available properties. Defaults to None.
        """
        if property_pool is None:
            from node_graph.properties import (
                property_pool,
            )  # Late import to avoid circular imports

        if isinstance(identifier, str):
            ItemClass = property_pool[identifier.upper()]
        elif isinstance(identifier, type) and issubclass(identifier, NodeProperty):
            ItemClass = identifier
        else:
            raise ValueError(f"Invalid identifier: {identifier}")

        return ItemClass(name, **data)

    def __str__(self) -> str:
        return f'{self.__class__.__name__}(name="{self.name}", value={self._value})'

    def __repr__(self) -> str:
        return self.__str__()
