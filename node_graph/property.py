class NodeProperty:
    """Node property.

    When variable is saved to a database, the type of the variable will
    be lost. We use this Property Class to label the type of the data,
    thus we can restore the data from database.

    The identifier is also helpful for the Editor to show the data in the
    GUI.
    """

    identifier = "NodeProperty"

    def __init__(self, name, description="", default=None, update=None) -> None:
        """_summary_

        Args:
            name (str): name of the varible
            options (list, optional): options of the varible. Defaults to [].
            description (str, optional): _description_. Defaults to "".
            default (_type_, optional): _description_. Defaults to None.
            extra (dict, optional): extra data, e.g. size for a vector. Defaults to {}.
            update (function, optional): The callback function when
                udpate the item. Defaults to None.
        """
        self.name = name
        self.description = description
        self.default = default
        self.update = update
        self._value = self.default

    def to_dict(self):
        """Data to be saved to database."""
        data = {
            "value": self.value,
            "name": self.name,
            "identifier": self.identifier,
            "serialize": self.get_serialize(),
            "deserialize": self.get_deserialize(),
            "metadata": self.get_metadata(),
        }
        return data

    def get_metadata(self):
        metadata = {"default": self.default}
        return metadata

    @classmethod
    def from_dict(cls, data):
        p = cls(data["name"])
        p.identifier = data["identifier"]
        p.value = data["value"]
        return p

    def update_from_dict(self, data):
        self.value = data["value"]

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, value):
        self.set_value(value)

    def set_value(self, value):
        # run the callback function
        self._value = value
        if self.update is not None:
            self.update()

    def copy(self):
        """Copy the property.
        We should not use this function! Because can not copy the callback function!!!
        """
        p = self.__class__(self.name, self.description, self.value, self.update)
        p._value = self._value
        return p

    @classmethod
    def new(cls, identifier, name=None, property_entry="node_graph.property", data={}):
        """Create a node from a identifier."""
        from node_graph.utils import get_entries
        import difflib
        property_pool = get_entries(property_entry)

        if identifier not in property_pool:
            items = difflib.get_close_matches(identifier, property_pool)
            if len(items) == 0:
                msg = "Identifier: {} is not defined.".format(identifier)
            else:
                msg = "Identifier: {} is not defined. Do you mean {}".format(
                    identifier, ", ".join(items)
                )
            raise Exception(msg)
        ItemClass = property_pool[identifier]
        item = ItemClass(name, **data)
        return item

    def __str__(self):
        return '{}(name="{}", value={})'.format(
            self.__class__.__name__, self.name, self._value
        )

    def __repr__(self):
        return '{}(name="{}", value={})'.format(
            self.__class__.__name__, self.name, self._value
        )
