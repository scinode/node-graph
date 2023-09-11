def register(pool, entries):
    """Add entries to the pool."""
    for entry in entries:
        if entry.identifier not in pool:
            pool[entry.identifier] = entry
        else:
            raise Exception("Entry: {} is already registered.".format(entry.identifier))


def get_entries(entry_point_name):
    """Get entries from the entry point."""
    from importlib.metadata import entry_points

    pool = {}
    for entry_point in entry_points().get(entry_point_name, []):
        new_entries = entry_point.load()
        register(pool, new_entries)
    return pool


def get_entry_by_identifier(identifier, entry_point):
    import difflib

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


def yaml_to_dict(data):
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
