from node_graph.property import NodeProperty
from node_graph.serializer import SerializeJson, SerializePickle
from typing import Any


class PropertyAny(NodeProperty, SerializePickle):
    """A new class for Any type."""

    identifier: str = "node_graph.any"
    allowed_types = (object,)  # Allow any type


class PropertyInt(NodeProperty, SerializeJson):
    """A new class for integer type."""

    identifier: str = "node_graph.int"
    allowed_types = (int, type(None))


class PropertyFloat(NodeProperty, SerializeJson):
    """A new class for float type."""

    identifier: str = "node_graph.float"
    allowed_types = (int, float, type(None))


class PropertyBool(NodeProperty, SerializeJson):
    """A new class for bool type."""

    identifier: str = "node_graph.bool"
    allowed_types = (bool, int, type(None))


class PropertyString(NodeProperty, SerializeJson):
    """A new class for string type."""

    identifier: str = "node_graph.string"
    allowed_types = (str, type(None))


class PropertyEnum(NodeProperty, SerializeJson):
    """A new class for enumeration type.

    Each option has:

    - identifier: identifier of the this option.
    - content: The true content of the this option.
    - description: Used for documentation and tooltips.

    >>> from node_graph.properties.built_in import PropertyEnum
    >>> enum = PropertyEnum("node_graph.enum",
                    options=[["add", "test_add", "add function"],
                            "sqrt", "test_sqrt", "sqrt function"],
                            "power", "test_power", "power function"]],
                    update=callback
                )
    >>> enum = "sqrt"
    >>> asset enum.value == "test_sqrt"
    """

    identifier: str = "node_graph.enum"

    def __init__(
        self, name, options=[], description="", default=None, update=None
    ) -> None:
        self._options = options
        # set the default value
        if default is None and None not in options:
            default = options[0][0]
        super().__init__(name, description, default, update)

    @property
    def keys(self):
        return [item[0] for item in self._options]

    @property
    def content(self):
        return self._options[self.keys.index(self._value)][1]

    @property
    def item_description(self):
        return self._options[self.keys.index(self._value)][2]

    def set_value(self, value):
        if value in self.keys:
            self._value = value
            # run the callback function
            if self.update is not None:
                self.update()
        else:
            raise Exception(f"{value} is not in the option list: {self.keys}.")

    def copy(self):
        p = self.__class__(
            self.name, self._options, self.description, self.value, self.update
        )
        p.value = self.value
        return p

    def get_metadata(self):
        metadata = {"default": self.default, "options": self._options}
        return metadata


# ====================================
# Vector
class PropertyVector(NodeProperty, SerializePickle):
    """node_graph Vector property"""

    identifier: str = "node_graph.vector"
    allowed_types = (list, tuple, type(None))
    allowed_item_types = (object, type(None))

    def __init__(self, name, description="", size=3, default=None, update=None) -> None:
        self.size = size
        default = [] if default is None else default
        super().__init__(name, description, default, update)

    def validate(self, value: Any) -> None:
        """Validate the given value based on allowed types."""
        if value is not None:
            if len(value) != self.size:
                raise ValueError(
                    f"Invalid size: Expected {self.size}, got {len(value)} instead."
                )
            for v in value:
                self.validate_item(v)

        return super().validate(value)

    def validate_item(self, value: Any) -> None:
        """Validate the given value based on allowed types."""
        if not isinstance(value, self.allowed_item_types):
            raise TypeError(
                f"Expected value of type {self.allowed_item_types}, got {type(value).__name__} instead."
            )

    def set_value(self, value: Any) -> None:
        self.validate(value)
        self._value = value
        if self.update:
            self.update()

    def copy(self):
        p = self.__class__(
            self.name, self.description, self.size, self.value, self.update
        )
        p.value = self.value
        return p

    def get_metadata(self):
        metadata = {"default": self.default, "size": self.size}
        return metadata


class PropertyIntVector(PropertyVector):
    """A new class for integer vector type."""

    identifier: str = "node_graph.int_vector"
    allowed_item_types = (int, type(None))

    def __init__(self, name, description="", size=3, default=None, update=None) -> None:
        default = [0] * size if default is None else default
        super().__init__(name, description, size, default, update)


class PropertyFloatVector(PropertyVector):
    """A new class for float vector type."""

    identifier: str = "node_graph.float_vector"
    allowed_item_types = (int, float, type(None))

    def __init__(self, name, description="", size=3, default=None, update=None) -> None:
        default = [0.0] * size if default is None else default
        super().__init__(name, description, size, default, update)


class PropertyBoolVector(PropertyVector):
    """A new class for bool vector type."""

    identifier: str = "node_graph.bool_vector"
    allowed_item_types = (int, bool, type(None))

    def __init__(self, name, description="", size=3, default=None, update=None) -> None:
        default = [False] * size if default is None else default
        super().__init__(name, description, size, default, update)


# =======================================
# matrix
class MatrixProperty(NodeProperty, SerializePickle):
    """node_graph Matrix property"""

    identifier: str = "node_graph.matrix"

    def __init__(
        self, name, description="", size=[3, 3], default=None, update=None
    ) -> None:
        self.size = size
        self._value = [] if default is None else default
        super().__init__(name, description, default, update)

    def validate(self, value: Any) -> None:
        """Validate the given value based on allowed types."""
        length = self.size[0] * self.size[1]
        if value is not None:
            if not (len(value) == length):
                raise ValueError(
                    f"Invalid size: Expected {length}, got {len(value)} instead."
                )
            for v in value:
                self.validate_item(v)

        return super().validate(value)

    def validate_item(self, value: Any) -> None:
        """Validate the given value based on allowed types."""
        if not isinstance(value, self.allowed_item_types):
            raise TypeError(
                f"Expected value of type {self.allowed_item_types}, got {type(value).__name__} instead."
            )

    def copy(self):
        p = self.__class__(
            self.name, self.description, self.size, self.value, self.update
        )
        p.value = self.value
        return p


class PropertyFloatMatrix(MatrixProperty):
    """A new class for float matrix type."""

    identifier: str = "node_graph.float_matrix"

    def __init__(
        self,
        name,
        description="",
        size=[3, 3],
        default=None,
        update=None,
    ) -> None:
        default = [0.0] * size[0] * size[1] if default is None else default
        super().__init__(name, description, size, default, update)


# =======================================
# dict, tuple, list with base type
def validate_base_type(value):
    if isinstance(value, dict):
        for _, subvalue in value.items():
            validate_base_type(subvalue)
    elif isinstance(value, (list, tuple)):
        for x in value:
            validate_base_type(x)
    else:
        if not isinstance(value, (int, float, str, bool)):
            raise Exception(
                "{} is not a base type (int, flot, str, bool).".format(value)
            )


class PropertyBaseDict(NodeProperty, SerializePickle):
    """node_graph BaseDict property.
    All the elements should be a base type (int, float, string, bool).
    """

    identifier: str = "node_graph.base_dict"

    def __init__(self, name, description="", default={}, update=None) -> None:
        default = {} if default is None else default
        super().__init__(name, description, default, update)

    def set_value(self, value):
        if isinstance(value, dict):
            validate_base_type(value)
            self._value = value
            # run the callback function
            if self.update is not None:
                self.update()
        else:
            raise Exception("{} is not a dict.".format(value))


class PropertyBaseList(NodeProperty, SerializePickle):
    """node_graph BaseList property.
    All the elements should be a base type (int, float, string, bool).
    """

    identifier: str = "BaseList"

    def __init__(self, name, description="", default=None, update=None) -> None:
        default = [] if default is None else default
        super().__init__(name, description, default, update)

    def set_value(self, value):
        if isinstance(value, (list, tuple)):
            validate_base_type(value)
            self._value = value
            # run the callback function
            if self.update is not None:
                self.update()
        else:
            raise Exception(
                f"Set property {self.name} failed. {value} is not a list or tuple."
            )
