from __future__ import annotations
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Dict, Any, Optional, Callable
from node_graph.socket_spec import SocketSpec, SocketView
from node_graph.executor import BaseExecutor, SafeExecutor
from .error_handler import ErrorHandlerSpec
import importlib
from enum import Enum

if TYPE_CHECKING:
    from node_graph.node import Node


class SchemaSource(str, Enum):
    """Defines how a node's schema is stored and reconstructed."""

    EMBEDDED = "embedded"
    HANDLE = "handle"
    CALLABLE = "callable"
    CLASS = "class"


@dataclass(frozen=True)
class NodeSpec:
    identifier: str
    schema_source: str = SchemaSource.EMBEDDED
    node_type: str = "Normal"
    catalog: str = "Others"
    inputs: Optional[SocketSpec] = None
    outputs: Optional[SocketSpec] = None
    executor: Optional[BaseExecutor] = None
    error_handlers: Dict[str, ErrorHandlerSpec] = field(default_factory=dict)
    attached_error_handlers: Dict[str, ErrorHandlerSpec] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    base_class_path: Optional[str] = None
    # not persisted directly; used at runtime
    base_class: Optional["Node"] = None
    version: Optional[str] = None

    def __post_init__(self):
        # Validate at least one of the base_class_path and base_class is provided
        if self.base_class is None and self.base_class_path is None:
            raise ValueError("Either base_class or base_class_path must be provided.")
        if self.base_class is not None and self.base_class_path is None:
            object.__setattr__(
                self,
                "base_class_path",
                f"{self.base_class.__module__}.{self.base_class.__name__}",
            )
        # if callable is not importable, we must embed the schema
        if self.executor and self.executor.mode != "module":
            object.__setattr__(self, "schema_source", SchemaSource.EMBEDDED)

    def to_dict(self) -> Dict[str, Any]:
        """
        Produce a compact, DB-ready representation of *this spec*.
        Modes:
          - embedded: store full spec under 'spec_schema'
          - module_handle: store only 'executor' (callable is a decorated handle)
        """
        # override schema_source
        if self.executor and isinstance(self.executor.callable, BaseHandle):
            object.__setattr__(self, "schema_source", SchemaSource.HANDLE)

        data: Dict[str, Any] = {
            "schema_source": self.schema_source.value,
            "identifier": self.identifier,
            "node_type": self.node_type,
            "catalog": self.catalog,
            "metadata": dict(self.metadata),
            "base_class_path": self.base_class_path,
        }
        if self.executor is not None:
            data["executor"] = self.executor.to_dict()
        if self.version:
            data["version"] = self.version

        if self.schema_source == SchemaSource.EMBEDDED:
            if self.inputs is not None:
                data["inputs"] = self.inputs.to_dict()
            if self.outputs is not None:
                data["outputs"] = self.outputs.to_dict()
            if self.error_handlers:
                data["error_handlers"] = {
                    name: eh.to_dict() for name, eh in self.error_handlers.items()
                }
        if self.attached_error_handlers:
            data["attached_error_handlers"] = {
                name: eh.to_dict() for name, eh in self.attached_error_handlers.items()
            }

        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> NodeSpec:
        """
        Rebuild a NodeSpec from a DB-ready representation produced by to_dict.
        """
        from node_graph.socket_spec import SocketSpec

        schema_source = SchemaSource(data.get("schema_source", SchemaSource.EMBEDDED))
        executor = SafeExecutor(**data["executor"]) if "executor" in data else None
        error_handlers = {
            name: ErrorHandlerSpec.from_dict(eh)
            for name, eh in data.get("error_handlers", {}).items()
        }
        attached_error_handlers = {
            name: ErrorHandlerSpec.from_dict(eh)
            for name, eh in data.get("attached_error_handlers", {}).items()
        }
        base_class = cls.get_base_class(data.get("base_class_path"))
        if schema_source == SchemaSource.EMBEDDED:
            inputs = SocketSpec.from_dict(data["inputs"]) if "inputs" in data else None
            outputs = (
                SocketSpec.from_dict(data["outputs"]) if "outputs" in data else None
            )
            spec = cls(
                identifier=data["identifier"],
                catalog=data.get("catalog", "Others"),
                node_type=data.get("node_type", "Normal"),
                schema_source=schema_source,
                inputs=inputs,
                outputs=outputs,
                executor=executor,
                error_handlers=error_handlers,
                metadata=data.get("metadata", {}),
                base_class_path=data.get("base_class_path"),
                version=data.get("version"),
            )
        elif schema_source == SchemaSource.CLASS:
            # Rebuild by calling the static method on the class
            spec = base_class._default_spec
        elif schema_source == SchemaSource.HANDLE:
            if executor is None:
                raise ValueError(
                    f"schema_source '{schema_source}' requires an executor"
                )

            func_or_handle = executor.callable
            if isinstance(func_or_handle, BaseHandle):
                spec = func_or_handle._spec
            else:
                raise RuntimeError(
                    "The executor.callable is not a BaseHandle; cannot reconstruct spec."
                )
        elif schema_source == SchemaSource.CALLABLE:
            if executor is None:
                raise ValueError(
                    f"schema_source '{schema_source}' requires an executor"
                )
            func_or_handle = executor.callable
            if isinstance(func_or_handle, BaseHandle):
                callable = func_or_handle._callable
            else:
                callable = func_or_handle
            spec = base_class.build(callable)
        else:
            raise ValueError(f"unrecognized schema_source '{schema_source}'")
        if attached_error_handlers:
            spec = replace(spec, attached_error_handlers=attached_error_handlers)
        return spec

    @staticmethod
    def get_base_class(base_class_path: str):
        """Return the concrete Node subclass to instantiate."""
        from node_graph.node import Node

        if base_class_path:
            module_name, class_name = base_class_path.rsplit(".", 1)
            return getattr(importlib.import_module(module_name), class_name)

        return Node

    @staticmethod
    def _resolve_decorator(decorator_path: Optional[str] = None) -> Callable:
        """Return the decorator callable if any."""
        from node_graph.decorator import node

        if decorator_path:
            module_name, func_name = decorator_path.rsplit(".", 1)
            return getattr(importlib.import_module(module_name), func_name)

        return node

    def to_node(
        self,
        name: str | None = None,
        uuid: str | None = None,
        graph=None,
        parent=None,
        metadata=None,
    ) -> "Node":
        """
        Materialize a Node from a NodeSpec with smart persistence:
          - If importable, default to compact persistence modes.
          - Otherwise, embed the schema to guarantee lossless restore.
        """
        Base = self.get_base_class(self.base_class_path)
        node = Base(
            name=name or self.identifier,
            uuid=uuid,
            graph=graph,
            parent=parent,
            metadata=metadata,
            spec=self,
        )
        return node


class BaseHandle:
    def __init__(self, spec: NodeSpec, get_current_graph, graph_class=None):
        self.identifier = spec.identifier
        self._spec = spec
        self._inputs_spec = spec.inputs
        self._outputs_spec = spec.outputs
        self._get_current_graph = get_current_graph
        self._graph_class = graph_class

    @property
    def inputs(self) -> SocketView:
        if self._inputs_spec is None:
            raise AttributeError(f"{self.identifier} has no inputs spec")
        return SocketView(self._inputs_spec)

    @property
    def outputs(self) -> SocketView:
        if self._outputs_spec is None:
            raise AttributeError(f"{self.identifier} has no outputs spec")
        return SocketView(self._outputs_spec)

    def __call__(self, *args, **kwargs):
        from node_graph.utils.function import prepare_function_inputs, is_function_like

        graph = self._get_current_graph()

        if graph is None:
            raise RuntimeError(
                f"No active graph available for {self._spec.identifier}."
            )
        node = graph.add_node(self._spec)
        zone = getattr(graph, "_active_zone", None)

        if zone:
            zone.children.add(node)
        exec_obj = self._spec.executor.callable if self._spec.executor else None
        if isinstance(exec_obj, BaseHandle) and hasattr(exec_obj, "_callable"):
            exec_obj = exec_obj._callable

        if is_function_like(exec_obj):
            prepared_inputs = prepare_function_inputs(exec_obj, *args, **kwargs)
        else:
            if args:
                raise TypeError(
                    f"{self.identifier} expects keyword-only inputs; got positional args {args!r}."
                )
            prepared_inputs = dict(kwargs)

        node.set_inputs(prepared_inputs)

        return node.outputs

    def build(self, /, *args, **kwargs):
        from node_graph.utils.graph import materialize_graph

        if self._spec.node_type.upper() != "GRAPH":
            raise TypeError(".build() is only available on graph specs")
        if self._spec.executor is None:
            raise RuntimeError("Spec has no executor")
        func = self._spec.executor.callable
        if isinstance(func, BaseHandle) and hasattr(func, "_callable"):
            func = func._callable
        if hasattr(func, "__globals__"):
            func.__globals__[func.__name__] = self

        return materialize_graph(
            func,
            self._spec.inputs,
            self._spec.outputs,
            self.identifier,
            self._graph_class,
            args=args,
            kwargs=kwargs,
        )


class NodeHandle(BaseHandle):
    def __init__(self, spec):
        from node_graph.manager import get_current_graph

        super().__init__(spec, get_current_graph)
