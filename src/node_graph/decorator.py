from __future__ import annotations
from typing import Any, Optional, Callable, List, Dict
import inspect
from .executor import RuntimeExecutor
from .error_handler import ErrorHandlerSpec, normalize_error_handlers
from .node import Node
from .node_spec import NodeSpec, hash_spec, NodeHandle, BaseHandle
from .socket_spec import infer_specs_from_callable, SocketSpec


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
    node.set_inputs(call_kwargs)
    outputs = [
        output for output in node.outputs if output._name not in ["_wait", "_outputs"]
    ]
    if len(outputs) == 1:
        return outputs[0]
    else:
        return node.outputs


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
    base_class: type | None = None,
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
        ident = identifier or func.__name__
        in_spec, out_spec = infer_specs_from_callable(func, inputs, outputs)
        handlers = normalize_error_handlers(error_handlers)
        spec = NodeSpec(
            identifier=ident,
            catalog=catalog,
            inputs=in_spec,
            outputs=out_spec,
            executor=RuntimeExecutor.from_callable(func),
            error_handlers=handlers or {},
            base_class_path=f"{base_class.__module__}.{base_class.__name__}"
            if base_class
            else None,
            metadata={"node_type": "Normal", "is_dynamic": True},
            version=hash_spec(ident, in_spec, out_spec, extra="callable"),
        )
        handle = NodeHandle(spec)
        handle._func = func
        return handle

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
        ident = identifier or func.__name__

        in_spec, out_spec = infer_specs_from_callable(func, inputs, outputs)

        spec = NodeSpec(
            identifier=ident,
            catalog=catalog,
            inputs=in_spec,
            outputs=out_spec,
            executor=RuntimeExecutor.from_callable(func),
            metadata={"node_type": "Graph", "is_dynamic": True, "graph_callable": True},
            version=hash_spec(ident, in_spec, out_spec, extra="graph"),
        )
        handle = NodeHandle(spec)
        handle._func = func
        return handle

    return wrap


class NodeDecoratorCollection:
    """Collection of node decorators."""

    node: Callable[..., Any] = staticmethod(decorator_node)
    graph: Callable[..., Any] = staticmethod(decorator_graph)

    # Alias '@node' to '@node.node'.
    def __call__(self, *args, **kwargs):
        return self.node(*args, **kwargs)


node: NodeDecoratorCollection = NodeDecoratorCollection()
