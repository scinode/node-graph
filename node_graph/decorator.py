from typing import Any, List, Dict, Tuple, Union, Optional, Callable
import inspect
from copy import deepcopy
import cloudpickle as pickle
import importlib
from node_graph.node import Node


def inspect_function(
    func: Callable[..., Any]
) -> Tuple[
    List[List[Union[str, Any]]],
    Dict[str, Dict[str, Union[Any, Optional[Any]]]],
    Optional[str],
    Optional[str],
]:
    """inspect the arguments of a function, and return a list of arguments
    and a list of keyword arguments, and a list of default values
    and a list of annotations

    Args:
        func (Callable[..., Any]): any function

    Returns:
        Tuple[List[List[Union[str, Any]]], Dict[str, Dict[str, Union[Any, Optional[Any]]]],
        Optional[str], Optional[str]]: (args, kwargs, defaults, annotations)
    """

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
            arg: List[Union[str, Any]] = [name, parameter.annotation]
            args.append(arg)
        elif parameter.kind == inspect.Parameter.POSITIONAL_OR_KEYWORD:
            if parameter.default is not inspect.Parameter.empty:
                kwargs[name] = {
                    "type": parameter.annotation,
                    "default": parameter.default,
                }
            else:
                args.append([name, parameter.annotation])
        elif parameter.kind == inspect.Parameter.VAR_POSITIONAL:
            var_args = name
        elif parameter.kind == inspect.Parameter.VAR_KEYWORD:
            var_kwargs = name

    return args, kwargs, var_args, var_kwargs


def python_type_to_socket_type(python_type: type) -> str:
    """Convert python type to socket type"""
    if python_type == int:
        return "node_graph.int"
    elif python_type == float:
        return "node_graph.float"
    elif python_type == str:
        return "node_graph.string"
    elif python_type == bool:
        return "node_graph.bool"
    else:
        return "node_graph.any"


def generate_input_sockets(
    func: Callable[..., Any],
    inputs: Optional[List[Dict[str, Any]]] = None,
    properties: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[
    List[str],
    List[str],
    Optional[str],
    Optional[str],
    List[Dict[str, Union[str, Dict[str, Union[str, Any]]]]],
]:
    """Generate input sockets from a function.
    If the input sockets is not given, then the function
    will be used to update the input sockets."""
    inputs = inputs or []
    properties = properties or []
    args, kwargs, var_args, var_kwargs = inspect_function(func)
    user_defined_input_names = [input["name"] for input in inputs] + [
        property["name"] for property in properties
    ]
    for arg in args:
        if arg[0] not in user_defined_input_names:
            inputs.append(
                {"identifier": python_type_to_socket_type(arg[1]), "name": arg[0]}
            )
    for name, kwarg in kwargs.items():
        if name not in user_defined_input_names:
            input = {
                "identifier": python_type_to_socket_type(kwarg["type"]),
                "name": name,
            }
            if kwarg["default"] is not None:
                # prop: [identifier, kwargs]
                input["property"] = {
                    "identifier": input["identifier"],
                    "default": kwarg["default"],
                }
            inputs.append(input)
    input_names = [input["name"] for input in inputs]
    if var_args is not None and var_args not in input_names:
        inputs.append({"identifier": "node_graph.any", "name": var_args})
    if var_kwargs is not None and var_kwargs not in input_names:
        inputs.append({"identifier": "node_graph.any", "name": var_kwargs})
    #
    arg_names = [arg[0] for arg in args]
    kwarg_names = [name for name in kwargs.keys()]
    # If the function has var_kwargs, and the user define input names does not
    # included in the args and kwargs, then add the user defined input names
    if var_kwargs is not None:
        for key in user_defined_input_names:
            if key not in args and key not in kwargs:
                if key == var_kwargs or key == var_args:
                    continue
                kwarg_names.append(key)
    return arg_names, kwarg_names, var_args, var_kwargs, inputs


def create_node(ndata: Dict[str, Any]) -> Callable[..., Any]:
    """Create a node class from node data.

    Args:
        ndata (Dict[str, Any]): node data

    Returns:
        Callable[..., Any]: _description_
    """

    NodeClass = ndata.get("node_class", Node)

    class DecoratedNode(NodeClass):
        identifier: str = ndata["identifier"]
        node_type: str = ndata.get("node_type", "NORMAL")
        catalog: str = ndata.get("catalog", "Others")

        def create_properties(self):
            properties = deepcopy(ndata.get("properties", []))
            for prop in properties:
                self.properties.new(prop.pop("identifier", "node_graph.any"), **prop)

        def create_sockets(self):
            outputs = deepcopy(ndata.get("outputs", []))
            inputs = deepcopy(ndata.get("inputs", []))

            for input in inputs:
                if isinstance(input, str):
                    input = {"identifier": "node_graph.any", "name": input}
                inp = self.inputs.new(
                    input.get("identifier", "node_graph.any"), input["name"]
                )
                prop = input.get("property", None)
                if prop is not None:
                    prop["name"] = input["name"]
                    # identifer, name, kwargs
                    inp.add_property(**prop)
                inp.link_limit = input.get("link_limit", 1)
            for output in outputs:
                if isinstance(output, str):
                    output = {"identifier": "node_graph.any", "name": output}
                identifier = output.pop("identifier", "node_graph.any")
                self.outputs.new(identifier, **output)
            self.args = ndata.get("args", [])
            self.kwargs = ndata.get("kwargs", [])
            self.var_args = ndata.get("var_args", None)
            self.var_kwargs = ndata.get("var_kwargs", None)

        def get_executor(self):
            executor = ndata.get("executor", {})
            return executor

    return DecoratedNode


def create_node_group(ngdata: Dict[str, Any]) -> Callable[..., Any]:
    """Create a node group class from node group data.

    Args:
        ngdata (Dict[str, Any]): node data

    Returns:
        Callable[..., Any]: _description_
    """

    NodeClass = ngdata.get("node_class", Node)

    class MyNodeGroup(NodeClass):
        identifier: str = ngdata["identifier"]
        node_type: str = "GROUP"
        catalog: str = ngdata.get("catalog", "Others")

        def get_default_node_group(self):
            nt = ngdata["nt"]
            nt.name = self.name
            nt.uuid = self.uuid
            nt.parent_node = self.uuid
            return ngdata["nt"]

    return MyNodeGroup


def decorator_node(
    identifier: Optional[str] = None,
    node_type: str = "Normal",
    properties: Optional[List[Dict[str, Any]]] = None,
    inputs: Optional[List[Dict[str, Any]]] = None,
    outputs: Optional[List[Dict[str, Any]]] = None,
    catalog: str = "Others",
    executor_type: str = "function",
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
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

    properties = properties or []
    inputs = inputs or []
    outputs = outputs or [{"identifier": "node_graph.any", "name": "result"}]

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:

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
    identifier: Optional[str] = None,
    properties: Optional[List[Dict[str, Any]]] = None,
    inputs: Optional[List[Dict[str, Any]]] = None,
    outputs: Optional[List[Dict[str, Any]]] = None,
    catalog: str = "Others",
    executor_type: str = "function",
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Generate a decorator that register a node group as a node.

    Attributes:
        indentifier (str): node identifier
        catalog (str): node catalog
        properties (list): node properties
        inputs (list): node inputs
        outputs (list): node outputs
    """

    properties = properties or []
    inputs = inputs or []
    outputs = outputs or []

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:

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
        node_outputs = [
            {"identifier": "node_graph.any", "name": output[1]} for output in outputs
        ]
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


def build_node(ndata: Dict[str, Any]) -> Callable[..., Any]:

    ndata.setdefault("properties", [])
    ndata.setdefault("inputs", [])
    ndata.setdefault("outputs", [{"identifier": "node_graph.any", "name": "result"}])
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

    node: Callable[..., Any] = staticmethod(decorator_node)
    group: Callable[..., Any] = staticmethod(decorator_node_group)

    __call__: Any = node  # Alias '@node' to '@node.node'.


node: NodeDecoratorCollection = NodeDecoratorCollection()
