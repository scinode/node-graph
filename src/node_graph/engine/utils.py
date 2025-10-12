from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple, Set
from collections import defaultdict, deque
from node_graph.link import NodeLink
from node_graph import NodeGraph
from node_graph.socket_spec import SocketSpec


def get_nested_dict(d: Dict, name: str, **kwargs) -> Any:
    """Get the value from a nested dictionary.
    If default is provided, return the default value if the key is not found.
    Otherwise, raise ValueError.
    For example:
    d = {"data": {"abc": {"xyz": 2}}}
    name = "data.abc.xyz"
    """

    keys = name.split(".")
    current = d
    for key in keys:
        if key not in current:
            if "default" in kwargs:
                return kwargs.get("default")
            else:
                if isinstance(current, dict):
                    avaiable_keys = current.keys()
                else:
                    avaiable_keys = []
                raise ValueError(f"{name} not exist. Available keys: {avaiable_keys}")
        current = current[key]
    return current


def merge_dicts(dict1: Any, dict2: Any) -> Any:
    """Recursively merges two dictionaries."""
    for key, value in dict2.items():
        if key in dict1 and isinstance(dict1[key], dict) and isinstance(value, dict):
            # Recursively merge dictionaries
            dict1[key] = merge_dicts(dict1[key], value)
        else:
            # Overwrite or add the key
            dict1[key] = value
    return dict1


def update_nested_dict(
    base: Optional[Dict[str, Any]], key_path: str, value: Any
) -> None:
    """
    Update or create a nested dictionary structure based on a dotted key path.

    This function allows updating a nested dictionary or creating one if `d` is `None`.
    Given a dictionary and a key path (e.g., "data.abc.xyz"), it will traverse
    or create the necessary nested structure to set the provided value at the specified
    key location. If intermediate dictionaries do not exist, they will be created.
    If the resulting dictionary is empty, it is set to `None`.

    Args:
        base (Dict[str, Any] | None): The dictionary to update, which can be `None`.
                                   If `None`, an empty dictionary will be created.
        key (str): A dotted key path string representing the nested structure.
        value (Any): The value to set at the specified key.

    Example:
        base = None
        key = "data.abc.xyz"
        value = 2
        After running:
            update_nested_dict(d, key, value)
        The result will be:
            base = {"data": {"abc": {"xyz": 2}}}

    Edge Case:
        If the resulting dictionary is empty after the update, it will be set to `None`.

    """

    if base is None:
        base = {}
    keys = key_path.split(".")
    current_key = keys[0]
    if len(keys) == 1:
        # Base case: Merge dictionaries or set the value directly.
        if isinstance(base.get(current_key), dict) and isinstance(value, dict):
            base[current_key] = merge_dicts(base[current_key], value)
        else:
            base[current_key] = value
    else:
        # Recursive case: Ensure the key exists and is a dictionary, then recurse.
        if current_key not in base or not isinstance(base[current_key], dict):
            base[current_key] = {}
        base[current_key] = update_nested_dict(
            base[current_key], ".".join(keys[1:]), value
        )

    return base


def update_nested_dict_with_special_keys(data: Dict[str, Any]) -> Dict[str, Any]:
    """Update the nested dictionary with special keys like "base.pw.parameters"."""
    # Remove None

    data = {k: v for k, v in data.items() if v is not None}
    #
    special_keys = [k for k in data.keys() if "." in k]
    for key in special_keys:
        value = data.pop(key)
        update_nested_dict(data, key, value)
    return data


def _collect_literals(node, raw=False) -> Dict[str, Any]:
    """
    Recursively collect literal values from the node's input namespace, excluding
    values that are overridden by links at schedule time.
    """
    from node_graph.utils import tag_socket_value

    tag_socket_value(node.inputs, only_uuid=True)
    return node.inputs._collect_values(raw=raw)


def _resolve_tagged_value(value: Any) -> Any:
    """
    Recursively unwrap TaggedValue instances to get their raw values.
    """
    from node_graph.socket import TaggedValue

    if isinstance(value, TaggedValue):
        return value.__wrapped__
    elif isinstance(value, dict):
        return {k: _resolve_tagged_value(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_resolve_tagged_value(v) for v in value]
    elif isinstance(value, tuple):
        return tuple(_resolve_tagged_value(v) for v in value)
    return value


def _scan_links_topology(
    ng: NodeGraph,
) -> Tuple[List[str], Dict[str, List[NodeLink]], Dict[str, Set[str]]]:
    """
    Build (1) a topological order, (2) incoming-links-per-node, and (3) a per-node set
    of required *output socket names* based on downstream edges.

    required_out_sockets helps us pre-register futures for only keys that will be needed
    by downstream nodes (plus DEFAULT_OUT, commonly used).
    """
    indeg: Dict[str, int] = {n: 0 for n in ng.get_node_names()}
    incoming: Dict[str, List[NodeLink]] = defaultdict(list)
    outgoing: Dict[str, List[Tuple[str, str]]] = defaultdict(
        list
    )  # src -> [(dst, to_sock_name)]
    required_out_sockets: Dict[str, Set[str]] = defaultdict(set)

    for lk in ng.links:
        src = lk.from_node.name
        dst = lk.to_node.name
        incoming[dst].append(lk)
        outgoing[src].append((dst, lk.to_socket._scoped_name))
        indeg[dst] = indeg.get(dst, 0) + 1
        indeg.setdefault(src, 0)

        # Track which output sockets of src are actually used downstream
        # (_wait and _outputs are handled specially later)
        from_sock = lk.from_socket._scoped_name
        if from_sock not in ("_wait", "_outputs"):
            required_out_sockets[src].add(from_sock)

    q = deque([n for n, d in indeg.items() if d == 0])
    order: List[str] = []
    while q:
        n = q.popleft()
        order.append(n)
        for (m, _dest_sock) in outgoing.get(n, []):
            indeg[m] -= 1
            if indeg[m] == 0:
                q.append(m)

    if len(order) != len(indeg):
        raise RuntimeError(
            "Cycle detected; cannot build Prefect flow from a cyclic graph."
        )

    return order, incoming, required_out_sockets


def _merge_multi_links_for_node(
    target_name: str,
    links_into_node: List[NodeLink],
    whole_task_future: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Build kwargs for a node by applying link semantics:
      - If exactly one link feeds an input socket:
          * from._wait     -> ignore (keep literal/namespace value)
          * from._outputs  -> pass the entire dict future for that from-node
          * else           -> pass that (from_node, from_socket) future
      - If multiple links feed the SAME input socket -> dict:
            { "{fromNode}_{fromSocket}": future, ... }
      - Unlinked inputs/literal namespaces are left to the literal collector in the flow.
    """
    # group by destination input socket name
    grouped: Dict[str, List[NodeLink]] = defaultdict(list)
    for lk in links_into_node:
        if lk.to_node.name == target_name:
            grouped[lk.to_socket._scoped_name].append(lk)

    kwargs: Dict[str, Any] = {}
    for to_sock, lks in grouped.items():
        if len(lks) == 1:
            lk = lks[0]
            from_name = lk.from_node.name
            from_sock = lk.from_socket._scoped_name
            if from_sock == "_wait":
                # wait edge --> don't override literal, just ensure the dependency is honored.
                # (Dependency is implicitly honored because we reference the source in futures elsewhere.)
                continue
            elif from_sock == "_outputs":
                # whole dict of source outputs (future)
                kwargs[to_sock] = whole_task_future[from_name]
            else:
                kwargs[to_sock] = get_nested_dict(
                    whole_task_future[from_name], from_sock, default=None
                )
        else:
            # multiple links into same input --> bundle as dict
            bundle: Dict[str, Any] = {}
            for lk in lks:
                from_name = lk.from_node.name
                from_sock = lk.from_socket._scoped_name
                if from_sock in ("_wait", "_outputs"):
                    # skip _wait and _outputs in multi-fan-in to avoid ambiguity
                    continue
                key = f"{from_name}_{from_sock}"
                bundle[key] = get_nested_dict(
                    whole_task_future[from_name], from_sock, default=None
                )
            kwargs[to_sock] = bundle

    return kwargs


def _ordered_field_names(spec: SocketSpec) -> list[str]:
    return list(spec.fields.keys())


def parse_outputs(
    results: Any,
    spec: SocketSpec | Dict[str, Any],
) -> Tuple[Optional[Dict[str, Any]]]:
    """Validate & convert *results* according to *spec*.

    Returns (outputs_dict, exit_code). If *exit_code* is not None, the caller should
    return it and ignore *outputs_dict*.
    """
    fields = spec.fields or {}
    is_dyn = bool(spec.dynamic)
    item_spec = spec.item if is_dyn else None

    # tuple -> map by order of fixed field names
    if isinstance(results, tuple):
        names = _ordered_field_names(spec)
        if len(names) != len(results):
            return None
        outs: Dict[str, Any] = {}
        for i, name in enumerate(names):
            child_spec = fields[name]
            outs[name] = results[i]
        return outs, None

    # dict
    if isinstance(results, dict):
        remaining = dict(results)
        outs: Dict[str, Any] = {}
        if len(fields) == 1 and not is_dyn:
            ((only_name, only_spec),) = fields.items()
            # if user used the same key as port name, use that value;
            if only_name in results:
                outs[only_name] = results.pop(only_name)
                if results:
                    print(
                        f"Found extra results that are not included in the output: {list(results.keys())}"
                    )
            else:
                # else treat the entire dict as the value for that single port.
                outs[only_name] = results
            return outs

        # fixed fields
        for name, child_spec in fields.items():
            if name in remaining:
                value = remaining.pop(name)
                outs[name] = value
            else:
                # If the field is explicitly required -> invalid output
                required = getattr(child_spec.meta, "required", None)
                if required is True:
                    print(f"Missing required output: {name}")
                    return None
        # dynamic items
        if is_dyn:
            if item_spec is None:
                print(
                    "Outputs marked dynamic but missing 'item' schema; treating as ANY."
                )
            for name, value in remaining.items():
                outs[name] = value
            return outs
        # not dynamic -> leftovers are unexpected (warn but continue)
        if remaining:
            print(
                f"Found extra results that are not included in the output: {list(remaining.keys())}"
            )
        return outs

    # single fixed output + non-dict/tuple scalar
    if len(fields) == 1 and not is_dyn:
        ((only_name, only_spec),) = fields.items()
        return {only_name: results}

    # empty output spec + None result
    if len(fields) == 0 and results is None:
        return {}

    return None
