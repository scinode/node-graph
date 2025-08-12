from __future__ import annotations
import functools
from typing import Any, List, Dict, Optional, Callable
import inspect
from node_graph.executor import NodeExecutor
from node_graph.node import Node
from node_graph.nodes.factory.function_node import DecoratedFunctionNodeFactory


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
    properties: Optional[Dict[str, Any]] = None,
    inputs: Optional[Dict[str, Any]] = None,
    outputs: Optional[Dict[str, Any]] = None,
    catalog: str = "Others",
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Generate a decorator that register a function as a NodeGraph node.
    After decoration, calling that function `func(x, y, ...)`
    dynamically creates a node in the current NodeGraph context
    instead of executing Python code directly.

    Attributes:
        indentifier (str): node identifier
        catalog (str): node catalog
        properties (dict): node properties
        inputs (dict): node inputs
        outputs (dict): node outputs
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        NodeCls = DecoratedFunctionNodeFactory.from_function(
            func=func,
            identifier=identifier,
            node_type=node_type,
            properties=properties,
            inputs=inputs,
            outputs=outputs,
            catalog=catalog,
        )

        return _make_wrapper(NodeCls, func)

    return decorator


def decorator_graph_builder(
    identifier: Optional[str] = None,
    properties: Optional[Dict[str, Any]] = None,
    inputs: Optional[Dict[str, Any]] = None,
    outputs: Optional[Dict[str, Any]] = None,
    catalog: str = "Others",
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Generate a decorator that register a function as a graph_builder node.

    Attributes:
        indentifier (str): node identifier
        catalog (str): node catalog
        properties (dict): node properties
        inputs (dict): node inputs
        outputs (dict): node outputs
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        from node_graph.nodes.builtins import GraphBuilderNode

        NodeCls = DecoratedFunctionNodeFactory.from_function(
            func=func,
            identifier=identifier,
            node_type="node_group",
            properties=properties,
            inputs=inputs,
            outputs=outputs,
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
