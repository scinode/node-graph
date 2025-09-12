from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, Type
import hashlib
import json
from node_graph.socket_spec import SocketSpec, SocketView
from node_graph.executor import BaseExecutor, SafeExecutor
from node_graph.node import Node
from .error_handler import ErrorHandlerSpec


@dataclass(frozen=True)
class NodeSpec:
    identifier: str
    node_type: str = "Normal"
    catalog: str = "Others"
    inputs: Optional[SocketSpec] = None
    outputs: Optional[SocketSpec] = None
    executor: Optional[BaseExecutor] = None
    error_handlers: Dict[str, ErrorHandlerSpec] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    base_class_path: Optional[str] = None
    # not persisted directly; used at runtime
    base_class: Optional[Type[Node]] = None
    version: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "identifier": self.identifier,
            "catalog": self.catalog,
            "metadata": dict(self.metadata),
        }
        if self.inputs is not None:
            d["inputs"] = self.inputs.to_dict()
        if self.outputs is not None:
            d["outputs"] = self.outputs.to_dict()
        if self.executor is not None:
            d["executor"] = self.executor.to_dict()
        if self.error_handlers:
            d["error_handlers"] = {
                name: eh.to_dict() for name, eh in self.error_handlers.items()
            }
        if self.version:
            d["version"] = self.version
        # prefer explicit path; otherwise derive from class
        path = self.base_class_path
        if path is None and self.base_class is not None:
            path = f"{self.base_class.__module__}.{self.base_class.__qualname__}"
        if path:
            d["base_class_path"] = path
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "NodeSpec":
        inputs = SocketSpec.from_dict(d["inputs"]) if "inputs" in d else None
        outputs = SocketSpec.from_dict(d["outputs"]) if "outputs" in d else None
        executor = SafeExecutor(**d["executor"]) if "executor" in d else None
        error_handlers = {
            name: ErrorHandlerSpec.from_dict(eh)
            for name, eh in d.get("error_handlers", {}).items()
        }
        return cls(
            identifier=d["identifier"],
            catalog=d.get("catalog", "Others"),
            inputs=inputs,
            outputs=outputs,
            executor=executor,
            error_handlers=error_handlers,
            metadata=d.get("metadata", {}),
            base_class_path=d.get("base_class_path"),
            version=d.get("version"),
        )

    def _resolve_base_class(self):
        """Return the concrete Node subclass to instantiate."""
        import importlib
        from node_graph.spec_node import SpecNode

        if self.base_class is not None:
            return self.base_class
        if self.base_class_path:
            module_name, class_name = self.base_class_path.rsplit(".", 1)
            return getattr(importlib.import_module(module_name), class_name)

        return SpecNode

    def to_node(
        self,
        name: str | None = None,
        uuid: str | None = None,
        graph=None,
        parent=None,
        metadata=None,
    ) -> "Node":
        """
        Materialize a Node from a NodeSpec:
          - copies identifier/catalog/metadata/executor
          - builds inputs/outputs from SocketSpec via NodeSocketNamespace._from_spec
        """
        Base = self._resolve_base_class()
        node = Base(
            name=name or self.identifier,
            uuid=uuid,
            graph=graph,
            parent=parent,
            metadata=metadata,
            spec=self,
            executor=self.executor,
            error_handlers=self.error_handlers,
        )
        return node


def hash_spec(
    identifier: str,
    inputs: SocketSpec | None,
    outputs: SocketSpec | None,
    extra: Any = None,
) -> str:
    def _ser(obj):
        if obj is None:
            return None
        if hasattr(obj, "to_dict"):
            return obj.to_dict()
        return obj

    payload = {
        "identifier": identifier,
        "inputs": _ser(inputs),
        "outputs": _ser(outputs),
        "extra": _ser(extra),
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


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
        if isinstance(exec_obj, BaseHandle) and hasattr(exec_obj, "_func"):
            exec_obj = exec_obj._func

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

        if self._spec.metadata.get("node_type", "").upper() != "GRAPH":
            raise TypeError(".build() is only available on graph specs")
        if self._spec.executor is None:
            raise RuntimeError("Spec has no executor")
        func = self._spec.executor.callable
        if isinstance(func, BaseHandle) and hasattr(func, "_func"):
            func = func._func
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
