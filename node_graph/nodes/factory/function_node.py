from node_graph.orm.mapping import type_mapping
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
from node_graph.config import builtin_inputs, builtin_outputs
from node_graph.executor import NodeExecutor
from .base import BaseNodeFactory


class DecoratedFunctionNodeFactory(BaseNodeFactory):
    """A factory to create specialized subclasses of Node from functions."""

    @classmethod
    def from_function(
        cls,
        func: Callable,
        identifier: Optional[str] = None,
        node_type: str = "Normal",
        properties: Optional[List[Tuple[str, str]]] = None,
        inputs: Optional[List[Union[str, dict]]] = None,
        outputs: Optional[List[Union[str, dict]]] = None,
        error_handlers: Optional[List[Dict[str, Any]]] = None,
        catalog: str = "Others",
        group_inputs: List[Tuple[str, str]] = None,
        group_outputs: List[Tuple[str, str]] = None,
        additional_data: Optional[Dict[str, Any]] = None,
    ):
        """
        Build the _DecoratedFunctionNode subclass from the function
        and the various decorator arguments.
        """
        from node_graph.decorator import generate_input_sockets

        identifier = identifier or func.__name__
        inputs = inputs or []
        properties = properties or []
        outputs = outputs or []
        error_handlers = error_handlers or []
        task_inputs = generate_input_sockets(
            func, inputs, properties, type_mapping=type_mapping
        )
        # Mark function inputs and outputs
        for input in task_inputs:
            input.setdefault("metadata", {})
            input["metadata"]["is_function_input"] = True
        for out in outputs:
            out.setdefault("metadata", {})
            out["metadata"]["is_function_output"] = True
        # add built-in sockets
        for input in builtin_inputs:
            task_inputs.append(input.copy())
        for output in builtin_outputs:
            outputs.append(output.copy())
        tdata = {
            "identifier": identifier,
            "metadata": {
                "node_type": node_type,
                "catalog": catalog,
                "group_inputs": group_inputs or [],
                "group_outputs": group_outputs or [],
            },
            "properties": properties,
            "inputs": task_inputs,
            "outputs": outputs,
        }
        tdata["executor"] = NodeExecutor.from_callable(func).to_dict()
        additional_data = additional_data or {}
        tdata.update(additional_data)

        NodeCls = cls(tdata)
        return NodeCls
