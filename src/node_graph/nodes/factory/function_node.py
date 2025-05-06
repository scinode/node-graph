from node_graph.orm.mapping import type_mapping
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
from node_graph.config import builtin_inputs, builtin_outputs
from node_graph.executor import NodeExecutor
from node_graph.utils import list_to_dict
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
        additional_data: Optional[Dict[str, Any]] = None,
        node_class: Optional[Callable] = None,
    ):
        """
        Build the _DecoratedFunctionNode subclass from the function
        and the various decorator arguments.
        """
        from node_graph.decorator import generate_input_sockets

        node_class = node_class or cls.default_base_class

        identifier = identifier or func.__name__
        inputs = inputs or []
        properties = properties or []
        outputs = outputs or []
        error_handlers = error_handlers or []
        node_inputs = generate_input_sockets(
            func, inputs, properties, type_mapping=type_mapping
        )
        # Mark function inputs and outputs
        node_outputs = {
            "name": "outputs",
            "identifier": node_class.SocketPool.any,
            "sockets": list_to_dict(outputs),
        }
        for out in node_outputs["sockets"].values():
            out.setdefault("metadata", {})
            out["metadata"]["function_socket"] = True
        # add built-in sockets
        for input in builtin_inputs:
            node_inputs["sockets"][input["name"]] = input.copy()
        for output in builtin_outputs:
            node_outputs["sockets"][output["name"]] = output.copy()

        tdata = {
            "identifier": identifier,
            "metadata": {
                "node_type": node_type,
                "catalog": catalog,
            },
            "properties": properties,
            "inputs": node_inputs,
            "outputs": node_outputs,
        }
        tdata["executor"] = NodeExecutor.from_callable(func).to_dict()
        if node_class:
            tdata["metadata"]["node_class"] = node_class
        tdata["default_name"] = func.__name__
        additional_data = additional_data or {}
        tdata.update(additional_data)

        NodeCls = cls(tdata)
        return NodeCls
