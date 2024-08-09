from typing import Dict, Any, Union
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
        entry = entry_point.load()
        if entry_point.name.upper() not in pool:
            pool[entry_point.name.upper()] = entry
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
    links = []
    for node in nodes:
        # metadata
        metadata = node.get("metadata", {})
        metadata["identifier"] = node.pop("identifier")
        node["metadata"] = metadata
        # properties
        properties = {}
        if node.get("properties"):
            for name, p in node["properties"].items():
                properties[name] = {"value": p}
        node["properties"] = properties
        # links
        if node.get("inputs"):
            for input in node["inputs"]:
                input["to_node"] = node["name"]
                links.append(input)
        ntdata["nodes"][node["name"]] = node
    ntdata["links"] = links
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
