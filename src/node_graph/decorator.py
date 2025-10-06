from __future__ import annotations
from typing import Any, Optional, Callable, List, Dict
import inspect
from .error_handler import ErrorHandlerSpec
from .node import Node
from .node_spec import NodeHandle, BaseHandle
from .socket_spec import SocketSpec


def build_node_from_callable(
    executor: Callable,
    inputs: Optional[SocketSpec | List[str]] = None,
    outputs: Optional[SocketSpec | List[str]] = None,
) -> Node:
    """Build task from a callable object.
    First, check if the executor is already a task.
    If not, check if it is a function or a class.
    If it is a function, build task from function.
    """

    # if it already has Node class, return it
    if (
        isinstance(executor, BaseHandle)
        or inspect.isclass(executor)
        and issubclass(executor, Node)
    ):
        return executor
    if callable(executor):
        return node(inputs=inputs, outputs=outputs)(executor)

    raise ValueError(f"The executor {executor} is not supported.")


def decorator_node(
    identifier: Optional[str] = None,
    inputs: Optional[SocketSpec | List[str]] = None,
    outputs: Optional[SocketSpec | List[str]] = None,
    error_handlers: Optional[Dict[str, ErrorHandlerSpec]] = None,
    catalog: str = "Others",
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Generate a decorator that register a function as a NodeGraph node.
    After decoration, calling that function `func(x, y, ...)`
    dynamically creates a node in the current NodeGraph context
    instead of executing Python code directly.

    Attributes:
        indentifier (str): node identifier
        catalog (str): node catalog
        inputs (dict): node inputs
        outputs (dict): node outputs
    """

    def wrap(func) -> NodeHandle:
        from node_graph.nodes.function_node import FunctionNode

        return FunctionNode.build(
            obj=func,
            identifier=identifier or func.__name__,
            catalog=catalog,
            input_spec=inputs,
            output_spec=outputs,
            error_handlers=error_handlers,
        )

    return wrap


def decorator_graph(
    identifier: Optional[str] = None,
    inputs: Optional[SocketSpec | list] = None,
    outputs: Optional[SocketSpec | list] = None,
    catalog: str = "Others",
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Generate a decorator that register a function as a graph node.

    Attributes:
        indentifier (str): node identifier
        catalog (str): node catalog
        inputs (dict): node inputs
        outputs (dict): node outputs
    """

    def wrap(func) -> NodeHandle:
        from node_graph.nodes.function_node import FunctionNode

        return FunctionNode.build(
            obj=func,
            identifier=identifier or func.__name__,
            node_type="graph",
            catalog=catalog,
            input_spec=inputs,
            output_spec=outputs,
        )

    return wrap


class NodeDecoratorCollection:
    """Collection of node decorators."""

    node: Callable[..., Any] = staticmethod(decorator_node)
    graph: Callable[..., Any] = staticmethod(decorator_graph)

    # Alias '@node' to '@node.node'.
    def __call__(self, *args, **kwargs):
        return self.node(*args, **kwargs)


node: NodeDecoratorCollection = NodeDecoratorCollection()
