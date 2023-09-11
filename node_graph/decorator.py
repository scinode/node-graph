from typing import Any


def inspect_function(func: Any):
    """inspect the arguments of a function, and return a list of arguments
    and a list of keyword arguments, and a list of default values
    and a list of annotations

    Args:
        func (Any): any function

    Returns:
        tuple: (args, kwargs, defaults, annotations)
    """
    import inspect

    # Get the signature of the function
    signature = inspect.signature(func)

    # Get the parameters of the function
    parameters = signature.parameters

    # Iterate over the parameters
    args = []
    kwargs = {}
    var_args = None
    var_kwargs = None
    for name, parameter in parameters.items():
        if parameter.kind == inspect.Parameter.POSITIONAL_ONLY:
            if parameter.annotation is not inspect.Parameter.empty:
                arg = [name, parameter.annotation]
            else:
                arg = [name, None]
            args.append(arg)
        elif parameter.kind == inspect.Parameter.POSITIONAL_OR_KEYWORD:
            kwargs[name] = {"type": parameter.annotation}
            if parameter.default is not inspect.Parameter.empty:
                kwargs[name]["default"] = parameter.default
            else:
                kwargs[name]["default"] = None
        elif parameter.kind == inspect.Parameter.VAR_POSITIONAL:
            var_args = name
        elif parameter.kind == inspect.Parameter.VAR_KEYWORD:
            var_kwargs = name

    return args, kwargs, var_args, var_kwargs


def python_type_to_socket_type(python_type):
    """Convert python type to socket type"""
    if python_type == int:
        return "Int"
    elif python_type == float:
        return "Float"
    elif python_type == str:
        return "String"
    elif python_type == bool:
        return "Bool"
    else:
        return "General"


def generate_input_sockets(func: Any, inputs=None, properties=None):
    """Generate input sockets from a function.
    If the input sockets is not given, then the function
    will be used to update the input sockets."""
    inputs = inputs or []
    properties = properties or []
    args, kwargs, var_args, var_kwargs = inspect_function(func)
    names = [input[1] for input in inputs] + [property[1] for property in properties]
    for arg in args:
        if arg[0] not in names:
            inputs.append([python_type_to_socket_type(arg[1]), arg[0]])
    for name, kwarg in kwargs.items():
        if name not in names:
            input = [python_type_to_socket_type(kwarg["type"]), name]
            if kwarg["default"] is not None:
                # prop: [identifier, kwargs]
                input.append({"property": [input[0], {"default": kwarg["default"]}]})
            inputs.append(input)
    if var_args is not None:
        inputs.append(["General", var_args])
    if var_kwargs is not None:
        inputs.append(["General", var_kwargs])
    #
    arg_names = [arg[0] for arg in args]
    kwarg_names = [name for name in kwargs.keys()]
    return arg_names, kwarg_names, var_args, var_kwargs, inputs


def create_node(ndata):
    """Create a node class from node data.

    Args:
        ndata (dict): node data

    Returns:
        _type_: _description_
    """
    from node_graph.node import Node

    Node = ndata.get("node_class", Node)

    class MyNode(Node):
        identifier: str = ndata["identifier"]
        node_type: str = ndata.get("node_type", "NORMAL")
        catalog = ndata.get("catalog", "Others")

        def create_properties(self):
            for prop in ndata.get("properties", []):
                kwargs = prop[2] if len(prop) > 2 else {}
                self.properties.new(prop[0], prop[1], **kwargs)

        def create_sockets(self):
            for input in ndata.get("inputs", []):
                inp = self.inputs.new(input[0], input[1])
                setting = input[2] if len(input) > 2 else {}
                prop = setting.get("property", None)
                if prop is not None:
                    kwargs = prop[1] if len(prop) > 1 else {}
                    # identifer, name, kwargs
                    inp.add_property(prop[0], input[1], **kwargs)
                inp.link_limit = setting.get("link_limit", 1)
            for output in ndata.get("outputs", []):
                self.outputs.new(output[0], output[1])
            self.args = ndata.get("args", [])
            self.kwargs = ndata.get("kwargs", [])
            self.var_args = ndata.get("var_args", None)
            self.var_kwargs = ndata.get("var_kwargs", None)

        def get_executor(self):
            executor = ndata.get("executor", {})
            return executor

    return MyNode


def create_node_group(ngdata):
    """Create a node group class from node group data.

    Args:
        ngdata (dict): node data

    Returns:
        _type_: _description_
    """
    from node_graph.node import Node

    Node = ngdata.get("node_class", Node)

    class MyNodeGroup(Node):
        identifier: str = ngdata["identifier"]
        node_type: str = "GROUP"
        catalog = ngdata.get("catalog", "Others")

        def get_default_node_group(self):
            nt = ngdata["nt"]
            nt.name = self.name
            nt.uuid = self.uuid
            nt.parent_node = self.uuid
            return ngdata["nt"]

    return MyNodeGroup


# decorator with arguments indentifier, args, kwargs, properties, inputs, outputs, executor
def decorator_node(
    identifier=None,
    node_type="Normal",
    properties=None,
    inputs=None,
    outputs=None,
    catalog="Others",
    executor_type="function",
):
    """Generate a decorator that register a function as a NodeGraph node.

    Attributes:
        indentifier (str): node identifier
        catalog (str): node catalog
        args (list): node args
        kwargs (dict): node kwargs
        properties (list): node properties
        inputs (list): node inputs
        outputs (list): node outputs
    """
    from node_graph.node import Node

    properties = properties or []
    inputs = inputs or []
    outputs = outputs or [["General", "result"]]

    def decorator(func):
        import cloudpickle as pickle

        nonlocal identifier

        if identifier is None:
            identifier = func.__name__

        # use cloudpickle to serialize function
        executor = {
            "executor": pickle.dumps(func),
            "type": executor_type,
            "is_pickle": True,
        }
        #
        # Get the args and kwargs of the function
        args, kwargs, var_args, var_kwargs, _inputs = generate_input_sockets(
            func, inputs, properties
        )
        ndata = {
            "node_class": Node,
            "identifier": identifier,
            "node_type": node_type,
            "args": args,
            "kwargs": kwargs,
            "var_args": var_args,
            "var_kwargs": var_kwargs,
            "properties": properties,
            "inputs": _inputs,
            "outputs": outputs,
            "executor": executor,
            "catalog": catalog,
        }
        node = create_node(ndata)
        func.identifier = identifier
        func.node = node
        return func

    return decorator


def decorator_node_group(
    identifier=None,
    properties=None,
    inputs=None,
    outputs=None,
    catalog="Others",
    executor_type="function",
):
    """Generate a decorator that register a node group as a node.

    Attributes:
        indentifier (str): node identifier
        catalog (str): node catalog
        properties (list): node properties
        inputs (list): node inputs
        outputs (list): node outputs
    """
    from node_graph.node import Node

    properties = properties or []
    inputs = inputs or []
    outputs = outputs or []

    def decorator(func):
        import cloudpickle as pickle

        nonlocal identifier, inputs, outputs

        if identifier is None:
            identifier = func.__name__
        # use cloudpickle to serialize function
        func.identifier = identifier
        func.group_outputs = outputs
        executor = {
            "executor": pickle.dumps(func),
            "type": executor_type,
            "is_pickle": True,
        }
        # Get the args and kwargs of the function
        args, kwargs, var_args, var_kwargs, _inputs = generate_input_sockets(
            func, inputs, properties
        )
        node_outputs = [["General", output[1]] for output in outputs]
        #
        node_type = "nodegroup"
        ndata = {
            "node_class": Node,
            "identifier": identifier,
            "args": args,
            "kwargs": kwargs,
            "var_args": var_args,
            "var_kwargs": var_kwargs,
            "node_type": node_type,
            "properties": properties,
            "inputs": _inputs,
            "outputs": node_outputs,
            "executor": executor,
            "catalog": catalog,
        }
        node = create_node(ndata)
        node.group_inputs = inputs
        node.group_outputs = outputs
        func.node = node
        return func

    return decorator


def build_node(ndata):
    import importlib
    from node_graph.node import Node

    ndata.setdefault("properties", [])
    ndata.setdefault("inputs", [])
    ndata.setdefault("outputs", [["General", "result"]])
    ndata.setdefault("node_class", Node)

    executor = ndata["executor"]
    name = executor.get("name", None)
    if not name:
        executor["path"], executor["name"] = executor["path"].split(".", 1)
    module = importlib.import_module("{}".format(executor["path"]))
    func = getattr(module, executor["name"])
    # Get the args and kwargs of the function
    args, kwargs, var_args, var_kwargs, _inputs = generate_input_sockets(
        func, ndata["inputs"], ndata["properties"]
    )
    ndata.update(
        {
            "args": args,
            "kwargs": kwargs,
            "var_args": var_args,
            "var_kwargs": var_kwargs,
        }
    )
    node = create_node(ndata)
    return node


class NodeDecoratorCollection:
    """Collection of node decorators."""

    node = staticmethod(decorator_node)
    group = staticmethod(decorator_node_group)

    __call__: Any = node  # Alias '@node' to '@node.node'.


node = NodeDecoratorCollection()
