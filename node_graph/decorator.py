from typing import Any, List, Dict, Tuple, Union, Optional, Callable
import inspect
import cloudpickle as pickle
import importlib
from node_graph.node import Node
from node_graph.orm.mapping import type_mapping as node_graph_type_mapping
from node_graph.utils import create_node


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


def generate_input_sockets(
    func: Callable[..., Any],
    inputs: Optional[List[Dict[str, Any]]] = None,
    properties: Optional[List[Dict[str, Any]]] = None,
    type_mapping: Optional[Dict[type, str]] = None,
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

    if type_mapping is None:
        type_mapping = node_graph_type_mapping
    inputs = inputs or []
    properties = properties or []
    args, kwargs, var_args, var_kwargs = inspect_function(func)
    user_defined_input_names = [input["name"] for input in inputs] + [
        property["name"] for property in properties
    ]
    for arg in args:
        if arg[0] not in user_defined_input_names:
            inputs.append(
                {
                    "identifier": type_mapping.get(arg[1], type_mapping["default"]),
                    "name": arg[0],
                }
            )
    for name, kwarg in kwargs.items():
        if name not in user_defined_input_names:
            input = {
                "identifier": type_mapping.get(kwarg["type"], type_mapping["default"]),
                "name": name,
            }
            if kwarg["default"] is not None:
                # prop: [identifier, kwargs]
                input["property"] = {
                    "identifier": input["identifier"],
                    "default": kwarg["default"],
                }
            inputs.append(input)
    # if var_args in input_names, set the link_limit to 1e6 and the identifier to namespace
    if var_args is not None:
        has_var_args = False
        for input in inputs:
            if input["name"] == var_args:
                input.setdefault("link_limit", 1e6)
                if (
                    input.get("identifier", type_mapping["namespace"])
                    != type_mapping["namespace"]
                ):
                    raise ValueError(
                        "Socket with var_args must have namespace identifier"
                    )
                input["identifier"] = type_mapping["namespace"]
                has_var_args = True
        if not has_var_args:
            inputs.append(
                {
                    "identifier": type_mapping["namespace"],
                    "name": var_args,
                    "link_limit": 1e6,
                }
            )
    if var_kwargs is not None:
        has_var_kwargs = False
        for input in inputs:
            if input["name"] == var_kwargs:
                input.setdefault("link_limit", 1e6)
                if (
                    input.get("identifier", type_mapping["namespace"])
                    != type_mapping["namespace"]
                ):
                    raise ValueError(
                        "Socket with var_args must have namespace identifier"
                    )
                input["identifier"] = type_mapping["namespace"]
                has_var_kwargs = True
        if not has_var_kwargs:
            inputs.append(
                {
                    "identifier": type_mapping["namespace"],
                    "name": var_kwargs,
                    "link_limit": 1e6,
                }
            )
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
            ng = ngdata["ng"]
            ng.name = self.name
            ng.uuid = self.uuid
            ng.parent_node = self.uuid
            return ngdata["ng"]

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
            "identifier": identifier,
            "metadata": {
                "node_type": node_type,
                "catalog": catalog,
                "node_class": {"module": "node_graph.node", "name": "Node"},
            },
            "args": args,
            "kwargs": kwargs,
            "var_args": var_args,
            "var_kwargs": var_kwargs,
            "properties": properties,
            "inputs": _inputs,
            "outputs": outputs,
            "executor": executor,
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
        executor = {
            "executor": pickle.dumps(func),
            "type": executor_type,
            "is_pickle": True,
        }
        # Get the args and kwargs of the function
        args, kwargs, var_args, var_kwargs, node_inputs = generate_input_sockets(
            func, inputs, properties
        )
        node_outputs = [
            {"identifier": "node_graph.any", "name": output[1]} for output in outputs
        ]
        #
        node_type = "nodegroup"
        ndata = {
            "identifier": identifier,
            "args": args,
            "kwargs": kwargs,
            "var_args": var_args,
            "var_kwargs": var_kwargs,
            "metadata": {
                "node_type": node_type,
                "catalog": catalog,
                "node_class": {"module": "node_graph.node", "name": "Node"},
                "group_inputs": inputs,
                "group_outputs": outputs,
            },
            "properties": properties,
            "inputs": node_inputs,
            "outputs": node_outputs,
            "executor": executor,
        }
        node = create_node(ndata)
        func.node = node
        return func

    return decorator


def build_node(ndata: Dict[str, Any]) -> Callable[..., Any]:

    ndata.setdefault("metadata", {})
    ndata.setdefault("properties", [])
    ndata.setdefault("inputs", [])
    ndata.setdefault("outputs", [{"identifier": "node_graph.any", "name": "result"}])
    ndata["metadata"].setdefault(
        "node_class", {"module": "node_graph.node", "name": "Node"}
    )

    executor = ndata["executor"]
    name = executor.get("name", None)
    if not name:
        executor["module"], executor["name"] = executor["module"].split(".", 1)
    module = importlib.import_module("{}".format(executor["module"]))
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
