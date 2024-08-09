from node_graph.property import NodeProperty
from node_graph.serializer import SerializeJson, SerializePickle


class PropertyAny(NodeProperty, SerializePickle):
    """A new class for Any type."""

    identifier: str = "node_graph.any"
    data_type = "Any"

    def __init__(self, name, description="", default=None, update=None) -> None:
        super().__init__(name, description, default, update)


class PropertyInt(NodeProperty, SerializeJson):
    """A new class for integer type."""

    identifier: str = "node_graph.int"
    data_type = "Int"

    def __init__(self, name, description="", default=None, update=None) -> None:
        super().__init__(name, description, default, update)

    def set_value(self, value):
        # run the callback function
        if isinstance(value, (int, type(None))):
            self._value = value
            if self.update is not None:
                self.update()
        else:
            raise Exception("{} is not a integer.".format(value))


class PropertyFloat(NodeProperty, SerializeJson):
    """A new class for float type."""

    identifier: str = "node_graph.float"
    data_type = "Float"

    def __init__(self, name, description="", default=None, update=None) -> None:
        super().__init__(name, description, default, update)

    def set_value(self, value):
        # run the callback function
        if isinstance(value, (int, float, type(None))):
            self._value = value
            if self.update is not None:
                self.update()
        else:
            raise Exception("{} is not a float.".format(value))


class PropertyBool(NodeProperty, SerializeJson):
    """A new class for bool type."""

    identifier: str = "node_graph.bool"
    data_type = "Bool"

    def __init__(self, name, description="", default=None, update=None) -> None:
        super().__init__(name, description, default, update)

    def set_value(self, value):
        # run the callback function
        if isinstance(value, (bool, int, type(None))):
            self._value = bool(value)
            if self.update is not None:
                self.update()
        else:
            raise Exception("{} is not a bool.".format(value))


class PropertyString(NodeProperty, SerializeJson):
    """A new class for string type."""

    identifier: str = "node_graph.string"
    data_type = "String"

    def __init__(self, name, description="", default=None, update=None) -> None:
        super().__init__(name, description, default, update)

    def set_value(self, value):
        if isinstance(value, (str, type(None))):
            self._value = value
            # run the callback function
            if self.update is not None:
                self.update()
        else:
            raise Exception("{} is not a string.".format(value))


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
    data_type = "Enum"

    def __init__(
        self, name, options=[], description="", default=None, update=None
    ) -> None:
        super().__init__(name, description, default, update)
        self._options = options
        # set the default value
        if default is None and None not in options:
            self._value = options[0][0]

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
    data_type = "Vector"

    def __init__(self, name, description="", size=3, default=[], update=None) -> None:
        super().__init__(name, description, default, update)
        self.size = size

    def copy(self):
        p = self.__class__(
            self.name, self.description, self.size, self.value, self.update
        )
        p.value = self.value
        return p


class PropertyIntVector(PropertyVector):
    """A new class for integer vector type."""

    identifier: str = "node_graph.int_vector"
    data_type = "IntVector"

    def __init__(
        self, name, description="", size=3, default=[0, 0, 0], update=None
    ) -> None:
        super().__init__(name, description, size, default, update)

    def set_value(self, value):
        # run the callback function
        if len(value) == self.size:
            for i in range(self.size):
                if isinstance(value[i], int):
                    self._value[i] = value[i]
                    if self.update is not None:
                        self.update()
                else:
                    raise Exception(
                        f"Set property {self.name} failed. {value[i]} is not a integer."
                    )
        else:
            raise Exception(
                "Length {} is not equal to the size {}.".format(len(value), self.size)
            )


class PropertyFloatVector(PropertyVector):
    """A new class for float vector type."""

    identifier: str = "node_graph.float_vector"
    data_type = "FloatVector"

    def __init__(
        self, name, description="", size=3, default=[0, 0, 0], update=None
    ) -> None:
        super().__init__(name, description, size, default, update)

    def set_value(self, value):
        # run the callback function
        if len(value) == self.size:
            for i in range(self.size):
                if isinstance(value[i], (int, float)):
                    self._value[i] = value[i]
                    if self.update is not None:
                        self.update()
                else:
                    raise Exception("{} is not a float.".format(value[i]))
        else:
            raise Exception(
                "Length {} is not equal to the size {}.".format(len(value), self.size)
            )

    def get_metadata(self):
        metadata = {"default": self.default, "size": self.size}
        return metadata


class PropertyBoolVector(PropertyVector):
    """A new class for bool vector type."""

    identifier: str = "node_graph.bool_vector"
    data_type = "BoolVector"

    def __init__(
        self, name, description="", size=3, default=[0, 0, 0], update=None
    ) -> None:
        super().__init__(name, description, size, default, update)

    def set_value(self, value):
        # run the callback function
        if len(value) == self.size:
            for i in range(self.size):
                if isinstance(value[i], (bool, int)):
                    self._value[i] = value[i]
                    if self.update is not None:
                        self.update()
                else:
                    raise Exception("{} is not a bool.".format(value[i]))
        else:
            raise Exception(
                "Length {} is not equal to the size {}.".format(len(value), self.size)
            )


# =======================================
# matrix
class MatrixProperty(NodeProperty, SerializePickle):
    """node_graph Matrix property"""

    identifier: str = "node_graph.matrix"
    data_type = "Matrix"

    def __init__(
        self, name, description="", size=[3, 3], default=[], update=None
    ) -> None:
        super().__init__(name, description, default, update)
        self.size = size

    def copy(self):
        p = self.__class__(
            self.name, self.description, self.size, self.value, self.update
        )
        p.value = self.value
        return p


class PropertyFloatMatrix(MatrixProperty):
    """A new class for float matrix type."""

    identifier: str = "node_graph.float_matrix"
    data_type = "FloatMatrix"

    def __init__(
        self,
        name,
        description="",
        size=[3, 3],
        default=[0, 0, 0, 0, 0, 0, 0, 0, 0],
        update=None,
    ) -> None:
        super().__init__(name, description, size, default, update)

    def set_value(self, value):
        import numpy as np

        # run the callback function
        self._value = np.zeros(self.size)
        if len(value) == self.size[0] and len(value[0]) == self.size[1]:
            for i in range(self.size[0]):
                for j in range(self.size[1]):
                    self._value[i][j] = value[i][j]
                    if self.update is not None:
                        self.update()
        else:
            raise Exception(
                "Length {} is not equal to the size {}.".format(len(value), self.size)
            )


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
    data_type = "BaseDict"

    def __init__(self, name, description="", default={}, update=None) -> None:
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
    data_type = "BaseList"

    def __init__(self, name, description="", default=[], update=None) -> None:
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
