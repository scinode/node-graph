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
    for node in nodes:
        node.setdefault("metadata", {})
        node.setdefault("inputs", [])
        node.setdefault("properties", [])
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
    from copy import deepcopy
    from node_graph.orm.mapping import type_mapping as node_graph_type_mapping
    from node_graph.node import Node

    NodeClass = ndata.get("node_class", Node)
    type_mapping = ndata.get("type_mapping", node_graph_type_mapping)

    class DecoratedNode(NodeClass):
        identifier: str = ndata["identifier"]
        node_type: str = ndata.get("metadata", {}).get("node_type", "NORMAL")
        catalog: str = ndata.get("metadata", {}).get("catalog", "Others")
        is_dynamic: bool = True

        def create_properties(self):
            properties = deepcopy(ndata.get("properties", []))
            for prop in properties:
                self.properties.new(
                    prop.pop("identifier", type_mapping["default"]), **prop
                )

        def create_sockets(self):
            outputs = deepcopy(ndata.get("outputs", []))
            inputs = deepcopy(ndata.get("inputs", []))

            for input in inputs:
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
            for output in outputs:
                if isinstance(output, str):
                    output = {"identifier": type_mapping["default"], "name": output}
                identifier = output.pop("identifier", type_mapping["default"])
                self.outputs.new(identifier, name=output["name"])
            self.args = ndata.get("args", [])
            self.kwargs = ndata.get("kwargs", [])
            self.var_args = ndata.get("var_args", None)
            self.var_kwargs = ndata.get("var_kwargs", None)

        def get_executor(self):
            executor = ndata.get("executor", {})
            return executor

    return DecoratedNode
