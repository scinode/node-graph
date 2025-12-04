from __future__ import annotations
from typing import Callable, List, Optional, Dict
from node_graph.socket_spec import infer_specs_from_callable, SocketSpec
from node_graph.task_spec import (
    TaskSpec,
    TaskHandle,
    SchemaSource,
)
from node_graph.executor import RuntimeExecutor
from node_graph.error_handler import ErrorHandlerSpec, normalize_error_handlers
from node_graph.task import Task


class FunctionTask(Task):
    """A task that wraps a Python callable (function or method)."""

    identifier: str = "node_graph.function_task"
    catalog: str = "Builtins"
    is_dynamic: bool = True

    @classmethod
    def build(
        cls,
        *,
        obj: Callable,
        identifier: Optional[str] = None,
        task_type: str = "Function",
        catalog: str = None,
        input_spec: Optional[SocketSpec | List[str]] = None,
        output_spec: Optional[SocketSpec | List[str]] = None,
        error_handlers: Optional[Dict[str, ErrorHandlerSpec]] = None,
        metadata: Optional[dict] = None,
        version: Optional[str] = None,
    ) -> TaskSpec:
        """
        - infers function I/O
        - optionally merges process-contributed I/O
        - optionally merges additional I/O
        - records *each* contribution in metadata
        """
        from node_graph.socket_spec import validate_socket_data

        input_spec = validate_socket_data(input_spec)
        output_spec = validate_socket_data(output_spec)
        func_in, func_out = infer_specs_from_callable(obj, input_spec, output_spec)
        error_handlers = normalize_error_handlers(error_handlers)
        metadata = dict(metadata or {})
        executor = RuntimeExecutor.from_callable(obj)
        # We always use the EMBEDDED schema for the function task, but when storing the spec in the DB,
        # we will check if the callable is a BaseHandler, and switch the schema_source to HANDLER accordingly.
        # This avoids cyclic import.
        schema_source = SchemaSource.EMBEDDED
        spec = TaskSpec(
            identifier=identifier or obj.__name__,
            schema_source=schema_source,
            task_type=task_type,
            catalog=catalog,
            inputs=func_in,
            outputs=func_out,
            executor=executor,
            error_handlers=error_handlers,
            base_class=cls,
            metadata=metadata,
            version=version,
        )
        handle = TaskHandle(spec)
        handle._callable = obj
        return handle
