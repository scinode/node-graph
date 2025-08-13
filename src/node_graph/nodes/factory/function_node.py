from __future__ import annotations

from node_graph.orm.mapping import type_mapping
from typing import Any, Callable, Dict, List, Optional
from node_graph.config import builtin_inputs, builtin_outputs
from node_graph.executor import NodeExecutor
from node_graph.utils import validate_socket_data
from .base import BaseNodeFactory
from ..utils import generate_input_sockets, generate_output_sockets


class DecoratedFunctionNodeFactory(BaseNodeFactory):
    """A factory to create specialized subclasses of Node from functions."""

    @classmethod
    def from_function(
        cls,
        func: Callable,
        identifier: Optional[str] = None,
        node_type: str = "Normal",
        properties: Optional[Dict[str, Any]] = None,
        inputs: Optional[Dict[str, Any]] = None,
        outputs: Optional[Dict[str, Any]] = None,
        error_handlers: Optional[List[Dict[str, Any]]] = None,
        catalog: str = "Others",
        additional_data: Optional[Dict[str, Any]] = None,
        node_class: Optional[Callable] = None,
    ):
        """Build the _DecoratedFunctionNode subclass from the function and decorator args."""
        node_class = node_class or cls.default_base_class
        identifier = identifier or func.__name__

        inputs = validate_socket_data(inputs) or {}
        properties = validate_socket_data(properties) or {}
        outputs = validate_socket_data(outputs) or {}
        error_handlers = error_handlers or []

        node_inputs = generate_input_sockets(
            func, inputs, properties, type_mapping=type_mapping
        )

        node_outputs = generate_output_sockets(func, outputs, type_mapping=type_mapping)
        # add built-ins without clobbering
        for inp in builtin_inputs:
            node_inputs["sockets"].setdefault(inp["name"], inp.copy())
        for out in builtin_outputs:
            node_outputs["sockets"].setdefault(out["name"], out.copy())

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
