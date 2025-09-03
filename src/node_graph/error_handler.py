from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Union
from node_graph.executor import NodeExecutor


@dataclass(frozen=True)
class ErrorHandlerSpec:
    """Container for a handler executor and its integer exit codes."""

    handler: NodeExecutor
    exit_codes: List[int]
    max_retries: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "handler": self.handler.to_dict(),
            "exit_codes": list(self.exit_codes),
            "max_retries": int(self.max_retries),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ErrorHandlerSpec":
        handler_exec = NodeExecutor(**d["handler"])
        exit_codes = [int(x) for x in d.get("exit_codes", [])]
        return cls(
            handler=handler_exec,
            exit_codes=exit_codes,
            max_retries=int(d.get("max_retries", 1)),
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


def normalize_error_handlers(value: Dict[str, Any] | None) -> List[ErrorHandlerSpec]:
    """Accept None | iterable of dict/ErrorHandlerSpec and normalize to a list[ErrorHandlerSpec]."""
    if not value:
        return {}
    out: Dict[str, ErrorHandlerSpec] = {}
    for name, item in value.items():
        if isinstance(item, ErrorHandlerSpec):
            out[name] = ErrorHandlerSpec(
                handler=item.handler,
                exit_codes=[int(x) for x in item.exit_codes],
                max_retries=int(item.max_retries),
            )
        else:
            # dict format:
            # {"handler": <callable|NodeExecutor|dict>, "exit_codes": [int,...], "max_retries": int}
            handler_exec = _as_executor(item["handler"])
            exit_codes = [int(x) for x in item.get("exit_codes", [])]
            max_retries = int(item.get("max_retries", 1))
            out[name] = ErrorHandlerSpec(
                handler=handler_exec, exit_codes=exit_codes, max_retries=max_retries
            )
    return out
