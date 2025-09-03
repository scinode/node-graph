from ..node_graph import NodeGraph
from typing import Any, Optional, Callable
from node_graph.socket_spec import SocketSpec


def _assign_wg_outputs(outputs: Any, wg: NodeGraph) -> None:
    """
    Inspect the raw outputs from the function and attach them to the NodeGraph.
    """
    from node_graph.socket import NodeSocket, NodeSocketNamespace

    if isinstance(outputs, NodeSocket):
        wg.outputs[0] = outputs
    elif isinstance(outputs, NodeSocketNamespace):
        for socket in outputs:
            # skip some built-in outputs from the task, e.g., the exit_code
            if socket._name not in wg.outputs and not wg.outputs._metadata.dynamic:
                # Should we raise an warning here?
                continue
            wg.outputs[socket._name] = socket
    elif isinstance(outputs, dict):
        wg.outputs = outputs
    elif isinstance(outputs, tuple):
        if len(outputs) != len(wg.outputs):
            raise ValueError(
                f"The length of the outputs {len(outputs)} does not match the length of the \
                    Graph task outputs {len(wg.outputs)}."
            )
        outputs_dict = {}
        for i, output in enumerate(outputs):
            outputs_dict[wg.outputs[i]._name] = output
        wg.outputs = outputs_dict
    else:
        wg.outputs[0] = outputs


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
    with graph_class(name=name, inputs=in_spec, outputs=out_spec) as wg:
        inputs = prepare_function_inputs(func, *args, **merged)
        wg.graph_inputs.set_inputs(inputs)
        tag_socket_value(wg.inputs)
        inputs = wg.inputs._value
        raw = func(**wg.inputs._value)
        _assign_wg_outputs(raw, wg)
        return wg
