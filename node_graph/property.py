from typing import Callable, Dict, Any, Union


class NodeProperty:
    """Node property.

    Property is the data which can be shown in the GUI.
    """

    property_entry: str = "node_graph.property"
    identifier: str = "NodeProperty"

    def __init__(
        self,
        name: str,
        description: str = "",
        default: Any = None,
        update: Callable[[], None] = None,
    ) -> None:
        """_summary_

        Args:
            name (str): name of the variable
            description (str, optional): _description_. Defaults to "".
            default (Any, optional): _description_. Defaults to None.
            update (Callable[[], None], optional): The callback function when
                update the item. Defaults to None.
        """
        self.name: str = name
        self.description: str = description
        self.default: Any = default
        self.update: Callable[[], None] = update
        self._value: Any = self.default

    def to_dict(self) -> Dict[str, Any]:
        """Data to be saved to database."""
        data: Dict[str, Any] = {
            "value": self.value,
            "name": self.name,
            "identifier": self.identifier,
            "serialize": self.get_serialize(),
            "deserialize": self.get_deserialize(),
            "metadata": self.get_metadata(),
        }
        return data

    def get_metadata(self) -> Dict[str, Any]:
        metadata: Dict[str, Any] = {"default": self.default}
        return metadata

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NodeProperty":
        p: NodeProperty = cls(data["name"])
        p.identifier = data["identifier"]
        p.value = data["value"]
        return p

    def update_from_dict(self, data: Dict[str, Any]) -> None:
        self.value = data["value"]

    @property
    def value(self) -> Any:
        return self._value

    @value.setter
    def value(self, value: Any) -> None:
        self.set_value(value)

    def set_value(self, value: Any) -> None:
        # run the callback function
        self._value = value
        if self.update is not None:
            self.update()

    def copy(self) -> "NodeProperty":
        """Copy the property.
        We should not use this function! Because can not copy the callback function!!!
        """
        p: NodeProperty = self.__class__(
            self.name, self.description, self.value, self.update
        )
        p._value = self._value
        return p

    @classmethod
    def new(
        cls,
        identifier: Union[str, type],
        name: str = None,
        data: Dict[str, Any] = {},
        property_pool: Dict[str, "NodeProperty"] = None,
    ) -> "NodeProperty":
        """Create a property from an identifier.
        When a plugin creates a property, it should provide its own property pool.
        Then call super().new(identifier, name, property_pool) to create a property.
        """
        if property_pool is None:
            from node_graph.properties import property_pool
        if isinstance(identifier, str):
            ItemClass: "NodeProperty" = property_pool[identifier.upper()]
        elif isinstance(identifier, type) and issubclass(identifier, NodeProperty):
            ItemClass = identifier
        else:
            raise Exception(
                f"Identifier {identifier} is not a property or property name."
            )

        item: NodeProperty = ItemClass(name, **data)
        return item

    def __str__(self) -> str:
        return '{}(name="{}", value={})'.format(
            self.__class__.__name__, self.name, self._value
        )

    def __repr__(self) -> str:
        return '{}(name="{}", value={})'.format(
            self.__class__.__name__, self.name, self._value
        )
