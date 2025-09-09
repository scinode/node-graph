from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Union
from node_graph.executor import NodeExecutor


@dataclass()
class ErrorHandlerSpec:
    """Container for a handler executor and its integer exit codes."""

    executor: NodeExecutor
    exit_codes: List[int]
    max_retries: int = 1
    retry: int = 0
    kwargs: Dict[str, Any] = None  # extra kwargs to pass to the handler

    def to_dict(self) -> Dict[str, Any]:
        return {
            "executor": self.executor.to_dict(),
            "exit_codes": list(self.exit_codes),
            "max_retries": int(self.max_retries),
            "retry": int(self.retry),
            "kwargs": self.kwargs or {},
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ErrorHandlerSpec":
        executor = NodeExecutor(**d["executor"])
        exit_codes = [int(x) for x in d.get("exit_codes", [])]
        return cls(
            executor=executor,
            exit_codes=exit_codes,
            max_retries=int(d.get("max_retries", 1)),
            retry=int(d.get("retry", 0)),
            kwargs=d.get("kwargs", {}),
        )


def _as_executor(obj: Union[NodeExecutor, Dict[str, Any], Any]) -> NodeExecutor:
    """Normalize a handler-like object to NodeExecutor.

    Accepts:
      - NodeExecutor
      - dict produced by NodeExecutor.to_dict()
      - callable (wrapped via NodeExecutor.from_callable)
    """
    if isinstance(obj, NodeExecutor):
        return obj
    if isinstance(obj, dict):
        return NodeExecutor(**obj)
    # fall back to callable
    return NodeExecutor.from_callable(obj)


def normalize_error_handlers(
    value: Dict[str, Any] | None
) -> Dict[str, ErrorHandlerSpec]:
    """Accept None | iterable of dict/ErrorHandlerSpec and normalize to a list[ErrorHandlerSpec]."""
    if not value:
        return {}
    out = {}
    for name, item in value.items():
        if isinstance(item, ErrorHandlerSpec):
            out[name] = ErrorHandlerSpec(
                executor=item.executor,
                exit_codes=[int(x) for x in item.exit_codes],
                max_retries=int(item.max_retries),
            )
        else:
            # dict format:
            # {"executor": <callable|NodeExecutor|dict>, "exit_codes": [int,...], "max_retries": int}
            handler_exec = _as_executor(item["executor"])
            exit_codes = [int(x) for x in item.get("exit_codes", [])]
            max_retries = int(item.get("max_retries", 1))
            out[name] = ErrorHandlerSpec(
                executor=handler_exec, exit_codes=exit_codes, max_retries=max_retries
            )
    return out
