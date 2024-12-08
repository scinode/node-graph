from typing import Dict, Any, Union, Callable, List
from importlib.metadata import entry_points
import sys
import difflib


def nodegaph_to_short_json(
    ngdata: Dict[str, Union[str, List, Dict]]
) -> Dict[str, Union[str, Dict]]:
    """Export a nodegaph to a rete js editor data."""
    ngdata_short = {
        "name": ngdata["name"],
        "uuid": ngdata["uuid"],
        "state": ngdata["state"],
        "nodes": {},
        "links": ngdata["links"],
    }
    #
    for name, node in ngdata["nodes"].items():
        # Add required inputs to nodes
        inputs = [
            {"name": name, "identifier": input["identifier"]}
            for name, input in node["inputs"].items()
            if name in node["args"]
            or (node["identifier"].upper() == "SHELLJOB" and name.startswith("nodes."))
        ]

        ngdata_short["nodes"][name] = {
            "label": node["name"],
            "node_type": node["metadata"]["node_type"].upper(),
            "inputs": inputs,
            "properties": {},
            "outputs": [],
            "position": node["position"],
            "children": node.get("children", []),
        }
    # Add links to nodes
    for link in ngdata["links"]:
        ngdata_short["nodes"][link["to_node"]]["inputs"].append(
            {
                "name": link["to_socket"],
            }
        )
        ngdata_short["nodes"][link["from_node"]]["outputs"].append(
            {
                "name": link["from_socket"],
            }
        )
    return ngdata_short


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
                self.add_property(
                    prop.pop("identifier", type_mapping["default"]), **prop
                )

        def create_sockets(self):
            outputs = deepcopy(ndata.get("outputs", {}))
            inputs = deepcopy(ndata.get("inputs", {}))

            for name in ndata["sorted_inputs_names"]:
                input = inputs[name]
                if isinstance(input, str):
                    input = {"identifier": type_mapping["default"], "name": input}
                property_data = input.pop("property_data", None)
                self.add_input(
                    input.get("identifier", type_mapping["default"]),
                    name=input["name"],
                    arg_type=input.get("arg_type", "kwargs"),
                    metadata=input.get("metadata", {}),
                    link_limit=input.get("link_limit", 1),
                    property_data=property_data,
                )
            for name in ndata["sorted_outputs_names"]:
                output = outputs[name]
                if isinstance(output, str):
                    output = {"identifier": type_mapping["default"], "name": output}
                identifier = output.get("identifier", type_mapping["default"])
                self.add_output(
                    identifier, name=output["name"], metadata=output.get("metadata", {})
                )

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


def get_arg_type(input: Any, args_data: dict) -> None:
    """Get the argument type from the input data."""
    if input.arg_type.upper() == "ARGS":
        args_data["args"].append(input.name)
    elif input.arg_type.upper() == "KWARGS":
        args_data["kwargs"].append(input.name)
    elif input.arg_type.upper() == "VAR_ARGS":
        if args_data["var_args"] is not None:
            raise ValueError("Only one VAR_ARGS is allowed")
        args_data["var_args"] = input.name
    elif input.arg_type.upper() == "VAR_KWARGS":
        if args_data["var_kwargs"] is not None:
            raise ValueError("Only one VAR_KWARGS is allowed")
        args_data["var_kwargs"] = input.name
