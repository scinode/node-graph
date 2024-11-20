from typing import Dict, Any, Union, Callable
from importlib.metadata import entry_points
import sys
import difflib


def get_entries(entry_point_name: str) -> Dict[str, Any]:
    """Get entries from the entry point."""
    pool: Dict[str, Any] = {}
    eps = entry_points()
    if sys.version_info >= (3, 10):
        group = eps.select(group=entry_point_name)
    else:
        group = eps.get(entry_point_name, [])
    for entry_point in group:
        if entry_point.name.upper() not in pool:
            pool[entry_point.name.upper()] = entry_point
        else:
            raise Exception("Entry: {} is already registered.".format(entry_point.name))
    return pool


def get_entry_by_identifier(identifier: str, entry_point: str) -> Any:
    node_pool = get_entries(entry_point)
    if identifier not in node_pool:
        items = difflib.get_close_matches(identifier, node_pool)
        if len(items) == 0:
            msg = "Identifier: {} is not defined.".format(identifier)
        else:
            msg = "Identifier: {} is not defined. Do you mean {}".format(
                identifier, ", ".join(items)
            )
        raise Exception(msg)
    NodeClass = node_pool[identifier]
    return NodeClass


def yaml_to_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """Convert yaml data into dict."""
    ntdata = data
    nodes = ntdata.pop("nodes")
    ntdata["nodes"] = {}
    for node in nodes:
        node.setdefault("metadata", {})
        node.setdefault("inputs", [])
        node.setdefault("outputs", [])
        node.setdefault("properties", [])
        build_sorted_names(node)
        ntdata["nodes"][node["name"]] = node
    ntdata.setdefault("ctrl_links", {})
    return ntdata


def deep_copy_only_dicts(
    original: Union[Dict[str, Any], Any]
) -> Union[Dict[str, Any], Any]:
    """Copy all nested dictionaries in a structure but keep
    the immutable values (such as integers, strings, or tuples)
    shared between the original and the copy"""
    if isinstance(original, dict):
        return {k: deep_copy_only_dicts(v) for k, v in original.items()}
    else:
        # Return the original value if it's not a dictionary
        return original


def build_sorted_names(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build sorted names for the given data.

    Args:
        data (Dict[str, Any]): The data dictionary containing inputs, outputs, and properties.

    Returns:
        Dict[str, Any]: The modified data dictionary with sorted names.

    """
    for key in ["inputs", "outputs", "properties"]:
        data.setdefault(key, {})
        if isinstance(data[key], list):
            # add list_index to each item
            for i, item in enumerate(data[key]):
                item["list_index"] = i
            sorted_names = [item["name"] for item in data[key]]
            data[key] = {item["name"]: item for item in data[key]}
        elif isinstance(data[key], dict):
            sorted_names = [
                name
                for name, _ in sorted(
                    ((name, item["list_index"]) for name, item in data[key].items()),
                    key=lambda x: x[1],
                )
            ]
        else:
            raise ValueError("Invalid data type for key: {}".format(key))

        data["sorted_" + key + "_names"] = sorted_names


def create_node(ndata: Dict[str, Any]) -> Callable[..., Any]:
    """Create a node class from node data.

    Args:
        ndata (Dict[str, Any]): node data

    Returns:
        Callable[..., Any]: _description_
    """
    from copy import deepcopy
    from node_graph.orm.mapping import type_mapping as node_graph_type_mapping
    import importlib

    build_sorted_names(ndata)

    ndata.setdefault("metadata", {})

    node_class = ndata["metadata"].get(
        "node_class", {"module": "node_graph.node", "name": "Node"}
    )
    try:
        module = importlib.import_module("{}".format(node_class.get("module", "")))
        NodeClass = getattr(module, node_class["name"])
    except Exception as e:
        raise Exception("Error loading node class: {}".format(e))

    type_mapping = ndata.get("type_mapping", node_graph_type_mapping)

    class DecoratedNode(NodeClass):
        identifier: str = ndata["identifier"].upper()
        node_type: str = ndata.get("metadata", {}).get("node_type", "NORMAL")
        catalog: str = ndata.get("metadata", {}).get("catalog", "Others")
        # group
        group_inputs = ndata["metadata"].get("group_inputs", [])
        group_outputs = ndata["metadata"].get("group_outputs", [])

        _executor = ndata.get("executor", None)
        is_dynamic: bool = True

        def create_properties(self):
            properties = deepcopy(ndata.get("properties", {}))
            for name in ndata["sorted_properties_names"]:
                prop = properties[name]
                self.properties.new(
                    prop.pop("identifier", type_mapping["default"]), **prop
                )

        def create_sockets(self):
            outputs = deepcopy(ndata.get("outputs", {}))
            inputs = deepcopy(ndata.get("inputs", {}))

            for name in ndata["sorted_inputs_names"]:
                input = inputs[name]
                if isinstance(input, str):
                    input = {"identifier": type_mapping["default"], "name": input}
                inp = self.inputs.new(
                    input.get("identifier", type_mapping["default"]), input["name"]
                )
                prop = input.get("property", None)
                if prop is not None:
                    prop["name"] = input["name"]
                    # identifer, name, kwargs
                    inp.add_property(
                        identifier=prop["identifier"],
                        name=prop["name"],
                        default=prop.get("default", None),
                    )
                inp.link_limit = input.get("link_limit", 1)
            for name in ndata["sorted_outputs_names"]:
                output = outputs[name]
                if isinstance(output, str):
                    output = {"identifier": type_mapping["default"], "name": output}
                identifier = output.pop("identifier", type_mapping["default"])
                self.outputs.new(identifier, name=output["name"])
            self.args = ndata.get("args", [])
            self.kwargs = ndata.get("kwargs", [])
            self.var_args = ndata.get("var_args", None)
            self.var_kwargs = ndata.get("var_kwargs", None)

        def get_metadata(self):
            metadata = super().get_metadata()
            metadata["node_class"] = node_class
            return metadata

    return DecoratedNode


def get_item_class(identifier: str, pool: Dict[str, Any], base_class) -> Any:
    """Get the item class from the identifier."""
    if isinstance(identifier, str):
        identifier = pool[identifier.upper()].load()
    if isinstance(identifier, type) and issubclass(identifier, base_class):
        ItemClass = identifier
    elif isinstance(getattr(identifier, "node", None), type) and issubclass(
        identifier.node, base_class
    ):
        ItemClass = identifier.node
    else:
        raise Exception(
            f"Identifier {identifier} is not a valid {base_class.__name__} class or entry point."
        )
    return ItemClass
