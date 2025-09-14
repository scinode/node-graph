from __future__ import annotations
from dataclasses import dataclass
from importlib.metadata import entry_points, EntryPoint


class Namespace:
    """A simple recursive namespace that allows attribute-based access to nested dictionaries, with tab completion."""

    def __init__(self, name: str = "Namespace"):
        self._name = name
        self._data = {}

    def __getattr__(self, name: str) -> EntryPoint:
        if name in super().__getattribute__("_data"):
            return super().__getattribute__("_data")[name]
        raise AttributeError(f"Namespace {self._name} has no attribute {name!r}")

    def __setattr__(self, name: str, value: Namespace | EntryPoint) -> None:
        if name in ["_data", "_name"]:
            super().__setattr__(name, value)
        else:
            self._data[name] = value

    def __dir__(self):
        """Enable tab completion by returning all available attributes."""
        return list(self._data.keys())

    def __repr__(self):
        return f"Namespace({self._data})"

    def __contains__(self, key: str) -> bool:
        """Allow checking if a key exists, including nested keys."""
        parts = key.split(".")
        current = self
        for part in parts:
            if part in current._data:
                current = current._data[part]
            else:
                return False
        return True

    def __iter__(self):
        """Allow iteration over stored items."""
        return iter(self._data.items())

    def __getitem__(self, key: str) -> EntryPoint | Namespace:
        """Allow dictionary-like access and support nested keys."""
        parts = key.split(".")
        current = self
        for part in parts:
            if part in current._data:
                current = current._data[part]
            else:
                raise KeyError(
                    f"Key {key!r} not found in Namespace {self._name}. "
                    f"Available keys are: {list(self._keys())}"
                )
        return current

    def __setitem__(self, key: str, value: EntryPoint | Namespace) -> None:
        """Allow dictionary-like setting and support nested keys."""
        parts = key.split(".")
        current = self
        for part in parts[:-1]:  # Traverse or create nested structures
            if part not in current._data:
                current._data[part] = Namespace(name=part)
            current = current._data[part]
        current._data[parts[-1]] = value  # Set the final value

    def _keys(self, prefix="") -> list[str]:
        """Return all keys, including nested keys, using dot notation."""
        all_keys = []
        for key, value in self._data.items():
            full_key = f"{prefix}.{key}" if prefix else key
            all_keys.append(full_key)
            if isinstance(value, Namespace):  # Recursively collect nested keys
                all_keys.extend(value._keys(prefix=full_key))
        return all_keys


class EntryPointPool:
    """
    NodePool is a hierarchical namespace that loads nodes from entry points.
    This version is designed to be used as an instance and supports tab completion.
    """

    def __init__(self, entry_point_group: str, name: str = "EntryPointPool") -> None:
        self._items = Namespace(name=name)
        self._is_loaded = False
        self._load_items(entry_point_group)

    def _load_items(self, entry_point_group: str) -> None:
        """Loads nodes into the internal hierarchical dictionary, if not already loaded."""
        import sys

        if self._is_loaded:
            return

        eps = entry_points()

        if sys.version_info >= (3, 10):
            group = eps.select(group=entry_point_group)
        else:
            group = eps.get(entry_point_group, [])

        for ep in group:
            key_parts = ep.name.lower().split(".")  # Use '.' to define nested levels
            current_level = self._items

            # Create the nested namespace structure
            for part in key_parts[:-1]:
                if not hasattr(current_level, part):
                    setattr(current_level, part, Namespace(name=part))
                current_level = getattr(current_level, part)

            final_key = key_parts[-1]
            if hasattr(current_level, final_key):
                raise Exception(f"Duplicate entry point name detected: {ep.name!r}")

            setattr(current_level, final_key, ep)

        self._is_loaded = True

    def __getattr__(self, name: str) -> EntryPoint:
        """Allow direct access to nodes via instance attributes."""
        return getattr(super().__getattribute__("_items"), name)

    def __dir__(self):
        """Enable tab completion for the node pool instance."""
        return dir(self._items)

    def __repr__(self):
        return f"NodePool({self._items})"

    def __contains__(self, key: str) -> bool:
        """Allow checking if a key exists in the node pool."""
        return key in self._items

    def __iter__(self):
        """Allow iteration over stored items."""
        return iter(self._items)

    def __getitem__(self, key: str) -> EntryPoint:
        """Allow dictionary-like access to the nodes."""
        return self._items[key]

    def __setitem__(self, key: str, value: EntryPoint | Namespace) -> None:
        """Allow dictionary-like setting and support nested keys."""
        self._items[key] = value

    def _keys(self) -> list[str]:
        """Return all keys, including nested keys."""
        return self._items._keys()


@dataclass
class RegistryHub:
    """Aggregates entry-point pools and a type-mapping for a given platform prefix.

    The prefix corresponds to entry point groups like:
        - "{prefix}.node"
        - "{prefix}.socket"
        - "{prefix}.property"
        - optional: "{prefix}.type_mapping" (dict providers)
    """

    node_pool: EntryPointPool
    socket_pool: EntryPointPool
    property_pool: EntryPointPool
    type_mapping: dict

    def resolve(self, tp: type) -> str:
        return self.type_mapping.get(tp, self.type_mapping.get("default"))

    @classmethod
    def from_prefix(
        cls,
        node_group: str = "node_graph.node",
        socket_group: str = "node_graph.socket",
        property_group: str = "node_graph.property",
        type_mapping_group: str = "node_graph.type_mapping",
        identifier_prefix: str = "node_graph",
    ) -> "RegistryHub":
        node_pool = EntryPointPool(entry_point_group=node_group, name="NodePool")
        node_pool["graph_level"] = node_pool[f"{identifier_prefix}.graph_level"]
        socket_pool = EntryPointPool(entry_point_group=socket_group, name="SocketPool")
        socket_pool["any"] = socket_pool[f"{identifier_prefix}.any"]
        socket_pool["namespace"] = socket_pool[f"{identifier_prefix}.namespace"]
        property_pool = EntryPointPool(
            entry_point_group=property_group, name="PropertyPool"
        )
        property_pool["any"] = property_pool[f"{identifier_prefix}.any"]

        # Merge type mappings from EP providers (optional group)
        tm: dict = {}
        eps = entry_points()
        group = (
            eps.select(group=f"{type_mapping_group}.type_mapping")
            if hasattr(eps, "select")
            else eps.get(f"{type_mapping_group}.type_mapping", [])
        )
        for ep in group:
            try:
                d = ep.load()
                if isinstance(d, dict):
                    tm.update(d)
            except Exception:
                # Silently ignore faulty EPs, keep core robust
                pass
        # Sensible defaults
        tm.setdefault("default", f"{identifier_prefix}.any")
        tm.setdefault("namespace", f"{identifier_prefix}.namespace")

        return cls(node_pool, socket_pool, property_pool, tm)


registry_hub = RegistryHub.from_prefix()
