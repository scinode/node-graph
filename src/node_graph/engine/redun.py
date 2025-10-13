from __future__ import annotations

import re
from typing import Any, Dict, Optional

from node_graph import NodeGraph
from node_graph.node_graph import BUILTIN_NODES

from .base import BaseEngine
from .provenance import ProvenanceRecorder
from .utils import (
    _scan_links_topology,
    _collect_literals,
    update_nested_dict_with_special_keys,
    _resolve_tagged_value,
    get_nested_dict,
)

_TASK_NAME_SANITIZE_RE = re.compile(r"[^0-9A-Za-z_]")
_GRAPH_OUTPUTS_KEY = "graph_outputs"


def _sanitize_task_name(*parts: str) -> str:
    name = "_".join(parts)
    return _TASK_NAME_SANITIZE_RE.sub("_", name)


from redun import task as redun_task  # type: ignore
from redun.config import Config as RedunConfig  # type: ignore
from redun.scheduler import Scheduler, TaskExpression  # type: ignore


@redun_task(name=_sanitize_task_name("ng", "get_nested"), cache=False)
def _redun_get_nested(d: Dict[str, Any], dotted: str, default=None):
    return get_nested_dict(d, dotted, default=default)


@redun_task(name=_sanitize_task_name("ng", "bundle"), cache=False)
def _redun_bundle(**kwargs: Any) -> Dict[str, Any]:
    return dict(kwargs)


def _default_config() -> "RedunConfig":  # pragma: no cover - simple helper
    if RedunConfig is None:
        raise RuntimeError("redun is required to use RedunEngine.")
    return RedunConfig(
        {
            "scheduler": {
                "backend": "sqlite",
                "db_uri": "sqlite:///:memory:",
            }
        }
    )


class RedunEngine(BaseEngine):
    """Execute NodeGraphs using redun's scheduler while recording provenance."""

    engine_kind = "redun"

    def __init__(
        self,
        name: str = "redun-flow",
        *,
        recorder: Optional[ProvenanceRecorder] = None,
        config: Optional["RedunConfig"] = None,
        scheduler: Optional["Scheduler"] = None,
    ):
        if Scheduler is None or redun_task is None:
            raise RuntimeError(
                "redun is not installed. Install `redun` to use RedunEngine."
            )
        super().__init__(name, recorder)
        self.config = config or _default_config()
        self.scheduler = scheduler or Scheduler(config=self.config)
        self._graph_pid: Optional[str] = None

    def _link_socket_value(
        self, from_name: str, from_socket: str, source_map: Dict[str, Any]
    ) -> Any:
        upstream = source_map[from_name]
        if isinstance(upstream, dict):
            return get_nested_dict(upstream, from_socket, default=None)
        if isinstance(upstream, TaskExpression):
            return _redun_get_nested(upstream, from_socket, default=None)
        return super()._link_socket_value(from_name, from_socket, source_map)

    def _link_bundle(self, payload: Dict[str, Any]) -> Any:
        return _redun_bundle(**payload)

    def _build_node_executor(self, node, label_kind: str):
        recorder = self.recorder
        fn = self._unwrap_callable(node)
        is_graph = self._is_graph_node(node)

        task_name = _sanitize_task_name("node", self.name, node.name)

        if fn is None:

            @redun_task(name=task_name, cache=False)
            def _noop(parent_pid: Optional[str], **kwargs: Any) -> Dict[str, Any]:
                pid = recorder.process_start(
                    node.name,
                    None,
                    flow_run_id=f"redun:{self.name}",
                    task_run_id=f"redun:{node.name}",
                    parent_pid=parent_pid,
                )
                recorder.record_inputs_payload(pid, kwargs)
                try:
                    outputs = dict(kwargs)
                    recorder.record_outputs_payload(pid, outputs, label_kind=label_kind)
                    recorder.process_end(pid, state="FINISHED")
                    return outputs
                except Exception as exc:
                    recorder.process_end(pid, state="FAILED", error=str(exc))
                    raise

            return _noop

        @redun_task(name=task_name, cache=False)
        def _node_task(parent_pid: Optional[str], **kwargs: Any) -> Dict[str, Any]:
            pid: Optional[str] = None
            if not is_graph:
                pid = recorder.process_start(
                    node.name,
                    fn,
                    flow_run_id=f"redun:{self.name}",
                    task_run_id=f"redun:{node.name}",
                    parent_pid=parent_pid,
                )
                recorder.record_inputs_payload(pid, kwargs)
            try:
                call_kwargs = kwargs if is_graph else _resolve_tagged_value(kwargs)
                res = fn(**call_kwargs)
                tagged = self._normalize_outputs(node, res, strict=False)
                if pid is not None:
                    recorder.record_outputs_payload(pid, tagged, label_kind=label_kind)
                    recorder.process_end(pid, state="FINISHED")
                return tagged
            except Exception as exc:
                if pid is not None:
                    recorder.process_end(pid, state="FAILED", error=str(exc))
                raise

        return _node_task

    def run(
        self,
        ng: NodeGraph,
        parent_pid: Optional[str] = None,
    ) -> Dict[str, Any]:
        if Scheduler is None:
            raise RuntimeError(
                "redun is not installed. Install `redun` to use RedunEngine."
            )

        order, incoming, _required = _scan_links_topology(ng)
        values: Dict[str, Any] = self._snapshot_builtins(ng)

        graph_pid = self._start_graph_run(ng, parent_pid)
        previous_pid = self._graph_pid
        self._graph_pid = graph_pid

        try:
            task_exprs: Dict[str, Any] = {}
            for name in order:
                if name in BUILTIN_NODES:
                    continue

                node = ng.nodes[name]
                label_kind = "return" if self._is_graph_node(node) else "create"
                executor = self._build_node_executor(node, label_kind=label_kind)

                kw = dict(_collect_literals(node))
                link_kwargs = self._build_link_kwargs(
                    target_name=name,
                    links=incoming.get(name, []),
                    source_map=values,
                )
                kw.update(link_kwargs)
                kw = update_nested_dict_with_special_keys(kw)

                task_expression = executor(graph_pid, **kw)
                # task_exprs[name] = task_expression
                values[name] = task_expression

            bundle_items: Dict[str, Any] = dict(task_exprs)
            graph_kwargs = self._build_link_kwargs(
                target_name="graph_outputs",
                links=incoming.get("graph_outputs", []),
                source_map=values,
            )
            graph_kwargs = update_nested_dict_with_special_keys(graph_kwargs)
            bundle_items[_GRAPH_OUTPUTS_KEY] = _redun_bundle(**graph_kwargs)

            resolved: Dict[str, Any] = {}
            if bundle_items:
                final_expr = _redun_bundle(**bundle_items)
                resolved = self._execute_expression(final_expr, cache=False) or {}

            graph_outputs = resolved.pop(_GRAPH_OUTPUTS_KEY, {}) if resolved else {}

            return self._finalize_graph_success(ng, graph_pid, graph_outputs)
        except Exception as exc:
            self._record_graph_failure(graph_pid, exc)
            raise
        finally:
            self._graph_pid = previous_pid

    def _run_subgraph(self, node, sub_ng: NodeGraph, parent_pid: Optional[str]) -> None:
        sub_engine = RedunEngine(
            name=f"{self.name}::{node.name}",
            recorder=self.recorder,
            config=self.config,
        )
        sub_engine.run(sub_ng, parent_pid=parent_pid)

    def _get_active_graph_pid(self) -> Optional[str]:
        return self._graph_pid

    def _execute_expression(self, expr, cache: bool):
        if Scheduler is None:
            raise RuntimeError(
                "redun is not installed. Install `redun` to use RedunEngine."
            )
        backend = getattr(self.scheduler, "backend", None)
        import types

        patched_methods = []
        if not cache and backend is not None:
            if hasattr(backend, "set_eval_cache"):
                original_set_eval_cache = backend.set_eval_cache

                def _noop_set_eval_cache(_self, *args, **kwargs):
                    return None

                backend.set_eval_cache = types.MethodType(_noop_set_eval_cache, backend)
                patched_methods.append(("set_eval_cache", original_set_eval_cache))

            if hasattr(backend, "record_value"):
                original_record_value = backend.record_value

                def _skip_record_value(_self, *args, **kwargs):
                    return None

                backend.record_value = types.MethodType(_skip_record_value, backend)
                patched_methods.append(("record_value", original_record_value))

            if hasattr(backend, "record_call_node"):
                original_record_call_node = backend.record_call_node

                def _skip_record_call_node(_self, *args, **kwargs):
                    return None

                backend.record_call_node = types.MethodType(
                    _skip_record_call_node, backend
                )
                patched_methods.append(("record_call_node", original_record_call_node))

        try:
            try:
                return self.scheduler.run(expr, cache=cache, store=cache)
            except TypeError:
                try:
                    return self.scheduler.run(expr, cache=cache)
                except TypeError:
                    return self.scheduler.run(expr)
        finally:
            for name, original in patched_methods:
                setattr(backend, name, original)
