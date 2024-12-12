from typing import Dict, Any, Union, Callable, List
from importlib.metadata import entry_points
import sys
import difflib


def list_to_dict(data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Convert list to dict."""
    if isinstance(data, dict):
        return data
    return {d["name"]: d for d in data}


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
        inputs = []
        for input in node["inputs"].values():
            metadata = input.get("metadata", {}) or {}
            if metadata.get("required", False):
                inputs.append(
                    {"name": input["name"], "identifier": input["identifier"]}
                )

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
        node["properties"] = list_to_dict(node.get("properties", {}))
        node["inputs"] = list_to_dict(node.get("inputs", {}))
        node["outputs"] = list_to_dict(node.get("outputs", {}))
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


def create_node(ndata: Dict[str, Any]) -> Callable[..., Any]:
    """Create a node class from node data.

    Args:
        ndata (Dict[str, Any]): node data

    Returns:
        Callable[..., Any]: _description_
    """
    from node_graph.orm.mapping import type_mapping as node_graph_type_mapping
    import importlib
    from copy import deepcopy

    ndata.setdefault("metadata", {})

    node_class = ndata["metadata"].get(
        "node_class", {"module_path": "node_graph.node", "callable_name": "Node"}
    )
    try:
        module = importlib.import_module("{}".format(node_class.get("module_path", "")))
        NodeClass = getattr(module, node_class["callable_name"])
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

        is_dynamic: bool = True

        def create_properties(self):
            # ndata is shared between all instances
            # deepcopy to avoid changing the original data
            properties = deepcopy(list_to_dict(ndata.get("properties", {})))
            for prop in properties.values():
                self.add_property(
                    prop.pop("identifier", type_mapping["default"]), **prop
                )

        def create_sockets(self):
            inputs = deepcopy(list_to_dict(ndata.get("inputs", {})))
            for input in inputs.values():
                if isinstance(input, str):
                    input = {"identifier": type_mapping["default"], "name": input}
                kwargs = {}
                if "property_data" in input:
                    kwargs["property_data"] = input.pop("property_data")
                if "sockets" in input:
                    kwargs["sockets"] = input.pop("sockets")
                self.add_input(
                    input.get("identifier", type_mapping["default"]),
                    name=input["name"],
                    metadata=input.get("metadata", {}),
                    link_limit=input.get("link_limit", 1),
                    **kwargs,
                )
            outputs = deepcopy(list_to_dict(ndata.get("outputs", {})))
            for output in outputs.values():
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

        def get_executor(self):
            return ndata.get("executor", None)

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


def get_arg_type(name: str, args_data: dict, arg_type: str = "kwargs") -> None:
    """Get the argument type from the input data."""
    if arg_type.upper() == "ARGS":
        args_data["args"].append(name)
    elif arg_type.upper() == "KWARGS":
        args_data["kwargs"].append(name)
    elif arg_type.upper() == "VAR_ARGS":
        if args_data["var_args"] is not None:
            raise ValueError("Only one VAR_ARGS is allowed")
        args_data["var_args"] = name
    elif arg_type.upper() == "VAR_KWARGS":
        if args_data["var_kwargs"] is not None:
            raise ValueError("Only one VAR_KWARGS is allowed")
        args_data["var_kwargs"] = name


def collect_values_inside_namespace(namespace: Dict[str, Any]) -> Dict[str, Any]:
    """Collect values inside the namespace."""
    values = {}
    for key, socket in namespace["sockets"].items():
        if "sockets" in socket:
            data = collect_values_inside_namespace(socket)
            if data:
                values[key] = data
        if "property" in socket:
            value = socket.get("property", {}).get("value")
            if value is not None:
                values[key] = value
    return values
