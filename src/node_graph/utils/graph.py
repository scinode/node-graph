from ..node_graph import NodeGraph
from typing import Any, Optional, Callable
from node_graph.socket_spec import SocketSpec


def _assign_graph_outputs(outputs: Any, graph: NodeGraph) -> None:
    """
    Inspect the raw outputs from the function and attach them to the NodeGraph.

    Rules:
      - None        -> no outputs
      - NodeSocket  -> map to first declared output
      - Namespace   -> iterate sockets; assign by name (respect non-dynamic outputs)
      - dict        -> every leaf value (including nested dicts) must be BaseSocket
      - tuple       -> every item must be BaseSocket; length must match declared outputs
    """
    from node_graph.socket import (
        BaseSocket,
        NodeSocket,
        NodeSocketNamespace,
        TaggedValue,
    )

    def _ensure_all_sockets_in_dict(d: dict, path: str = "outputs") -> None:
        for k, v in d.items():
            subpath = f"{path}.{k}"
            if isinstance(v, dict):
                _ensure_all_sockets_in_dict(v, path=subpath)
            elif not isinstance(v, (BaseSocket, TaggedValue)):
                raise TypeError(
                    f"Invalid output at '{subpath}': expected BaseSocket or TaggedValue, got {type(v).__name__}."
                )

    if outputs is None:
        if len(graph.outputs) != 0:
            raise ValueError(
                "The function returned None, but the Graph node declares outputs. "
                "Either remove the declared outputs or ensure the function returns them."
            )
        return

    elif isinstance(outputs, (NodeSocket, TaggedValue)):
        # Single socket -> assign to first declared output slot
        graph.outputs[0] = outputs

    elif isinstance(outputs, NodeSocketNamespace):
        # if this is a dynamic namespace, we should link the top-level outputs
        if outputs._metadata.dynamic:
            graph.outputs = outputs

        for socket in outputs:
            if (
                socket._name not in graph.outputs
                and not graph.outputs._metadata.dynamic
            ):
                if socket._name.startswith("_"):
                    # Allow internal names to pass through even if not declared.
                    # This is useful for internal sockets that don't need
                    # to be exposed as a Graph output.
                    continue
                raise ValueError(
                    "Output socket name "
                    f"'{socket._name}' not declared in Graph node outputs.\n\n"
                    "How to fix:\n"
                    "1) Make graph outputs dynamic if you want to return arbitrary names:\n"
                    "   • `outputs = dynamic(Any)`\n"
                    "     (then returning arbitrary sockets is allowed)\n"
                    "2) Declare this output explicitly on the Graph:\n"
                    f"   • e.g. `outputs = namespace({socket._name}=Any, <some_other_name>=Any)`\n"
                    "3) Expose task outputs instead of inventing new names:\n"
                    f"   • e.g. `outputs = namespace({socket._name}=some_task.outputs, <some_other_name>=some_task.outputs)`\n"
                )
            graph.outputs[socket._name] = socket

    elif isinstance(outputs, dict):
        _ensure_all_sockets_in_dict(outputs)
        # If you also want to enforce declared names when not dynamic, do it here (optional).
        graph.outputs = outputs

    elif isinstance(outputs, tuple):
        if len(outputs) != len(graph.outputs):
            raise ValueError(
                f"The length of the outputs {len(outputs)} does not match the length of the "
                f"Graph node outputs {len(graph.outputs)}."
            )
        for i, output in enumerate(outputs):
            if not isinstance(output, (BaseSocket, TaggedValue)):
                raise TypeError(
                    f"Invalid output at index {i}: expected Socket or TaggedValue, got {type(output).__name__}."
                )
        outputs_dict = {
            graph.outputs[i]._name: output for i, output in enumerate(outputs)
        }
        graph.outputs = outputs_dict

    else:
        raise TypeError(
            f"Unsupported output type {type(outputs).__name__}. Must be one of "
            "Socket, TaggedValue, dict, tuple, or None."
        )


def materialize_graph(
    func: Callable,
    in_spec: SocketSpec,
    out_spec: SocketSpec,
    identifier: str = None,
    graph_class: type = None,
    *,
    args: tuple,
    kwargs: dict,
    var_kwargs: Optional[dict] = None,
) -> NodeGraph:
    """
    Run func(*args, **kwargs, **(var_kwargs or {})) inside a NodeGraph,
    assign its outputs and return the NodeGraph.
    """
    from node_graph.utils import tag_socket_value
    from node_graph.utils.function import prepare_function_inputs

    if graph_class is None:
        from node_graph import NodeGraph

        graph_class = NodeGraph

    merged = {**kwargs, **(var_kwargs or {})}
    name = identifier or func.__name__
    with graph_class(name=name, inputs=in_spec, outputs=out_spec) as graph:
        inputs = prepare_function_inputs(func, *args, **merged)
        graph.graph_inputs.set_inputs(inputs)
        tag_socket_value(graph.inputs)
        inputs = graph.inputs._collect_values(raw=False)
        raw = func(**inputs)
        _assign_graph_outputs(raw, graph)
        return graph
