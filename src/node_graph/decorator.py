from __future__ import annotations
import functools
from typing import Any, List, Dict, Tuple, Union, Optional, Callable
import inspect
from node_graph.executor import NodeExecutor
from node_graph.node import Node
from node_graph.orm.mapping import type_mapping as node_graph_type_mapping
from node_graph.nodes.factory.function_node import DecoratedFunctionNodeFactory
from node_graph.utils import list_to_dict


def set_node_arguments(call_args, call_kwargs, node):
    input_names = node.inputs._get_keys()
    for i, value in enumerate(call_args):
        if i < len(input_names):
            node.inputs[input_names[i]].value = value
        else:
            # Does not support var_args yet
            raise TypeError(
                f"Too many positional arguments. expects {len(input_names)} but you supplied {len(call_args)}."
            )
    node.set(call_kwargs)
    outputs = [
        output for output in node.outputs if output._name not in ["_wait", "_outputs"]
    ]
    if len(outputs) == 1:
        return outputs[0]
    else:
        return node.outputs


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
        elif parameter.kind in [
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        ]:
            kwargs[name] = {"type": parameter.annotation}
            if parameter.default is not inspect.Parameter.empty:
                kwargs[name]["default"] = parameter.default
                kwargs[name]["has_default"] = True
            else:
                kwargs[name]["has_default"] = False
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
) -> List[Dict[str, Union[str, Dict[str, Union[str, Any]]]]]:
    """Generate input sockets from a function.
    If the input sockets is not given, then the function
    will be used to update the input sockets."""

    if type_mapping is None:
        type_mapping = node_graph_type_mapping
    if inputs is None:
        inputs = []
    if properties is None:
        properties = []
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
                    "metadata": {
                        "arg_type": "args",
                        "required": True,
                        "function_socket": True,
                    },
                }
            )
    for name, kwarg in kwargs.items():
        if name not in user_defined_input_names:
            identifier = type_mapping.get(kwarg["type"], type_mapping["default"])
            input = {
                "identifier": identifier,
                "name": name,
                "metadata": {
                    "arg_type": "kwargs",
                    "required": True,
                    "function_socket": True,
                },
                "property": {"identifier": identifier},
            }
            if kwarg.get("has_default", False):
                input["property"]["default"] = kwarg["default"]
                input["metadata"]["required"] = False
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
                input.setdefault("metadata", {})
                input["metadata"]["arg_type"] = "var_args"
                has_var_args = True
        if not has_var_args:
            inputs.append(
                {
                    "identifier": type_mapping["namespace"],
                    "name": var_args,
                    "metadata": {"arg_type": "var_args", "function_socket": True},
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
                input.setdefault("metadata", {})
                input["metadata"].update({"arg_type": "var_kwargs", "dynamic": True})
                has_var_kwargs = True
        if not has_var_kwargs:
            inputs.append(
                {
                    "identifier": type_mapping["namespace"],
                    "name": var_kwargs,
                    "metadata": {
                        "arg_type": "var_kwargs",
                        "dynamic": True,
                        "function_socket": True,
                    },
                    "link_limit": 1e6,
                }
            )
    final_inputs = {
        "name": "inputs",
        "identifier": "node_graph.namespace",
        "sockets": list_to_dict(inputs),
        "metadata": {"dynamic": var_kwargs is not None},
    }
    return final_inputs


def build_node_from_callable(
    executor: Callable,
    inputs: Optional[List[str | dict]] = None,
    outputs: Optional[List[str | dict]] = None,
) -> Node:
    """Build task from a callable object.
    First, check if the executor is already a task.
    If not, check if it is a function or a class.
    If it is a function, build task from function.
    """
    from node_graph.nodes.factory.function_node import DecoratedFunctionNodeFactory

    # if it already has Node class, return it
    if (
        hasattr(executor, "_NodeCls")
        and inspect.isclass(executor._NodeCls)
        and issubclass(executor._NodeCls, Node)
        or inspect.isclass(executor)
        and issubclass(executor, Node)
    ):
        return executor
    if isinstance(executor, str):
        executor = NodeExecutor(module_path=executor).executor
    if callable(executor):
        return DecoratedFunctionNodeFactory.from_function(
            executor, inputs=inputs, outputs=outputs
        )

    raise ValueError(f"The executor {executor} is not supported.")


def _make_wrapper(NodeCls, original_callable):
    """
    Common wrapper that, when called, adds a node to the current graph
    and returns the outputs.
    """

    @functools.wraps(original_callable)
    def wrapper(*call_args, **call_kwargs):
        from node_graph.manager import get_current_graph

        graph = get_current_graph()
        if graph is None:
            raise RuntimeError(
                f"No active Graph available for {original_callable.__name__}."
            )
        node = graph.add_node(NodeCls)
        active_zone = getattr(graph, "_active_zone", None)
        if active_zone:
            active_zone.children.add(node)
        outputs = set_node_arguments(call_args, call_kwargs, node)
        return outputs

    # Expose the NodeCls on the wrapper if you want
    wrapper._NodeCls = NodeCls
    wrapper._func = original_callable
    return wrapper


def decorator_node(
    identifier: Optional[str] = None,
    node_type: str = "Normal",
    properties: Optional[List[Dict[str, Any]]] = None,
    inputs: Optional[List[Dict[str, Any]]] = None,
    outputs: Optional[List[Dict[str, Any]]] = None,
    catalog: str = "Others",
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Generate a decorator that register a function as a NodeGraph node.
    After decoration, calling that function `func(x, y, ...)`
    dynamically creates a node in the current NodeGraph context
    instead of executing Python code directly.

    Attributes:
        indentifier (str): node identifier
        catalog (str): node catalog
        properties (list): node properties
        inputs (list): node inputs
        outputs (list): node outputs
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        node_outputs = outputs or [{"identifier": "node_graph.any", "name": "result"}]
        NodeCls = DecoratedFunctionNodeFactory.from_function(
            func=func,
            identifier=identifier,
            node_type=node_type,
            properties=properties,
            inputs=inputs,
            outputs=node_outputs,
            catalog=catalog,
        )

        return _make_wrapper(NodeCls, func)

    return decorator


def decorator_graph_builder(
    identifier: Optional[str] = None,
    properties: Optional[List[Dict[str, Any]]] = None,
    inputs: Optional[List[Dict[str, Any]]] = None,
    outputs: Optional[List[Dict[str, Any]]] = None,
    catalog: str = "Others",
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Generate a decorator that register a function as a graph_builder node.

    Attributes:
        indentifier (str): node identifier
        catalog (str): node catalog
        properties (list): node properties
        inputs (list): node inputs
        outputs (list): node outputs
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        from node_graph.nodes.builtins import GraphBuilderNode

        node_outputs = [
            {"identifier": "node_graph.any", "name": output["name"]}
            for output in outputs or []
        ]
        NodeCls = DecoratedFunctionNodeFactory.from_function(
            func=func,
            identifier=identifier,
            node_type="node_group",
            properties=properties,
            inputs=inputs,
            outputs=node_outputs,
            catalog=catalog,
            node_class=GraphBuilderNode,
        )

        return _make_wrapper(NodeCls, func)

    return decorator


class NodeDecoratorCollection:
    """Collection of node decorators."""

    node: Callable[..., Any] = staticmethod(decorator_node)
    graph_builder: Callable[..., Any] = staticmethod(decorator_graph_builder)

    # Alias '@node' to '@node.node'.
    def __call__(self, *args, **kwargs):
        return self.node(*args, **kwargs)


node: NodeDecoratorCollection = NodeDecoratorCollection()
