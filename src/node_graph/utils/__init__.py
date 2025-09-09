from __future__ import annotations
from typing import Dict, Any, Union, List


def get_executor_from_path(path: dict | str) -> Any:
    """Get the executor from the path."""
    import importlib

    if isinstance(path, dict):
        module_path = path["module_path"]
        callable_name = path["callable_name"]
    elif isinstance(path, str):
        parts = path.split(".")
        if len(parts) < 2:
            raise ValueError(
                "module_path must contain at least one dot to separate "
                "the module from the callable (e.g. 'mymodule.myfunc')"
            )
        callable_name = parts[-1]
        module_path = ".".join(parts[:-1])
    module = importlib.import_module(module_path)
    executor = getattr(module, callable_name)

    return executor


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
        for input in node["input_sockets"]["sockets"].values():
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
    for link in ngdata_short["links"]:
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
    # remove the inputs socket of "graph_inputs"
    if "graph_inputs" in ngdata_short["nodes"]:
        ngdata_short["nodes"]["graph_inputs"]["inputs"] = []
    # remove the empty graph-level nodes
    for name in ["graph_inputs", "graph_outputs", "graph_ctx"]:
        if name in ngdata_short["nodes"]:
            node = ngdata_short["nodes"][name]
            if len(node["inputs"]) == 0 and len(node["outputs"]) == 0:
                del ngdata_short["nodes"][name]

    return ngdata_short


def yaml_to_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """Convert yaml data into dict."""
    ntdata = data
    nodes = ntdata.pop("nodes")
    ntdata["nodes"] = {}
    for node in nodes:
        node.setdefault("metadata", {})
        node["metadata"]["identifier"] = node.pop("identifier", None)
        node["properties"] = node.get("properties", {})
        node["inputs"] = node.get("inputs", {})
        node["outputs"] = node.get("outputs", {})
        ntdata["nodes"][node["name"]] = node
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


def collect_values_inside_namespace(
    namespace: Dict[str, Any], include_none: bool = True
) -> Dict[str, Any]:
    """Collect values inside the namespace."""
    values = {}
    for key, socket in namespace.get("sockets", {}).items():
        if "sockets" in socket:
            data = collect_values_inside_namespace(socket, include_none=include_none)
            if data:
                values[key] = data
        if "property" in socket:
            value = socket.get("property", {}).get("value")
            if value is None and not include_none:
                continue
            values[key] = value
    return values


def valid_name_string(s: str) -> bool:
    """
    Check whether the input string s contains only alphanumeric characters and underscores.
    If not, raise a ValueError with a clean message.

    Args:
        s: The string to validate.

    Returns:
        True if s is valid.

    Raises:
        ValueError: if s contains any character other than A-Z, a-z, 0-9 or underscore.
    """
    import re

    if not isinstance(s, str):
        raise ValueError(f"Invalid name: {s!r}: must be a string")

    if " " in s:
        raise ValueError(f"Invalid name: {s!r}: spaces are not allowed")

    if not re.fullmatch(r"[A-Za-z0-9_]+", s):
        raise ValueError(
            f"Invalid name: {s!r}. Only letters, digits and underscores are allowed"
        )


def socket_value_id_mapping(socket):
    """Create a mapping of value IDs to sockets in a NodeSocketNamespace."""
    from node_graph.socket import NodeSocketNamespace

    mapping = {}
    for sub_socket in socket._sockets.values():
        if isinstance(sub_socket, NodeSocketNamespace):
            sub_mapping = socket_value_id_mapping(sub_socket)
            for value_id, socket_list in sub_mapping.items():
                if value_id in mapping:
                    mapping[value_id].extend(socket_list)
                else:
                    mapping[value_id] = socket_list
        else:
            value_id = sub_socket.property._value_id
            if sub_socket.property.value is None:
                continue
            if value_id in mapping:
                mapping[value_id].append(sub_socket)
            else:
                mapping[value_id] = [sub_socket]
    return mapping


def tag_socket_value(socket: "NodeSocket") -> "NodeSocket":
    """Use a tagged object for the socket's property value."""
    from node_graph.socket import NodeSocketNamespace, TaggedValue

    if isinstance(socket, NodeSocketNamespace):
        for sub_socket in socket._sockets.values():
            tag_socket_value(sub_socket)
    else:
        # replace the socket's property value directly with a TaggedValue
        # this avoids triggering the value setter
        if socket.property:
            if socket.property.value is not None:
                socket.property.value = TaggedValue(
                    socket.property.value, socket=socket
                )
