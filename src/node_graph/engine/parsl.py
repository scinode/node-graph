from __future__ import annotations

from typing import Any, Dict, Optional

from node_graph import NodeGraph
from node_graph.node_graph import BUILTIN_NODES
from node_graph.socket import TaggedValue
from .provenance import ProvenanceRecorder
from .base import BaseEngine
from .utils import (
    _collect_literals,
    _resolve_tagged_value,
    _scan_links_topology,
    update_nested_dict_with_special_keys,
)

import parsl
from parsl import load
from parsl.app.app import AppFuture, python_app
from parsl.config import Config
from parsl.executors.threads import ThreadPoolExecutor


@python_app
def _parsl_get_nested(d: Dict[str, Any], dotted: str, default=None) -> Any:
    from .utils import get_nested_dict

    return get_nested_dict(d, dotted, default=default)


@python_app
def _parsl_bundle(**kwargs: Any) -> Dict[str, Any]:
    return kwargs


def _default_config() -> "Config":
    if Config is None:  # pragma: no cover - safeguarded by importorskip
        raise RuntimeError("Parsl is not installed.")
    return Config(
        executors=[ThreadPoolExecutor(max_threads=4)],
        strategy=None,
    )


def _ensure_dfk(config: "Config") -> "parsl.dataflow.dflow.DataFlowKernel":
    assert parsl is not None  # mypy safeguard
    try:
        return parsl.dfk()
    except Exception:
        return load(config)


class ParslEngine(BaseEngine):
    """
    Run NodeGraphs using Parsl python apps while recording provenance.
    """

    engine_kind = "parsl"

    def __init__(
        self,
        name: str = "parsl-flow",
        *,
        recorder: Optional[ProvenanceRecorder] = None,
        config: Optional["Config"] = None,
        dfk: Optional["parsl.dataflow.dflow.DataFlowKernel"] = None,
    ):
        if parsl is None:  # pragma: no cover - surfaced via importorskip
            raise RuntimeError(
                "Parsl is not installed. Install `parsl` to use ParslEngine."
            )
        super().__init__(name, recorder)
        self.config = config or _default_config()
        self._dfk = dfk
        self._graph_pid: Optional[str] = None

    def _link_socket_value(
        self, from_name: str, from_socket: str, source_map: Dict[str, Any]
    ) -> Any:
        upstream = source_map[from_name]
        if isinstance(upstream, AppFuture):
            return _parsl_get_nested(upstream, from_socket, default=None)
        return super()._link_socket_value(from_name, from_socket, source_map)

    def _link_bundle(self, payload: Dict[str, Any]) -> Any:
        return _parsl_bundle(**payload)

    def _build_node_executor(self, node, label_kind: str):
        fn = self._unwrap_callable(node)
        recorder = self.recorder
        is_graph = self._is_graph_node(node)

        if fn is None:

            @python_app
            def _noop_app(parent_pid: Optional[str], **kwargs: Any):
                resolved_kwargs = self._resolve_app_futures(kwargs)
                pid = recorder.process_start(
                    node.name,
                    None,
                    flow_run_id=None,
                    task_run_id=None,
                    parent_pid=parent_pid,
                )
                recorder.record_inputs_payload(pid, resolved_kwargs)
                try:
                    outputs = dict(resolved_kwargs)
                    recorder.record_outputs_payload(pid, outputs, label_kind=label_kind)
                    recorder.process_end(pid, state="FINISHED")
                    return outputs
                except Exception as exc:
                    recorder.process_end(pid, state="FAILED", error=str(exc))
                    raise

            return _noop_app

        @python_app
        def _node_app(parent_pid: Optional[str], **kwargs: Any):
            pid: Optional[str] = None
            resolved_kwargs = self._resolve_app_futures(kwargs)
            if not is_graph:
                pid = recorder.process_start(
                    node.name,
                    fn,
                    flow_run_id=None,
                    task_run_id=None,
                    parent_pid=parent_pid,
                )
                recorder.record_inputs_payload(pid, resolved_kwargs)
            try:
                call_kwargs = (
                    resolved_kwargs
                    if is_graph
                    else _resolve_tagged_value(resolved_kwargs)
                )
                res = fn(**call_kwargs)
                tagged = self._normalize_outputs(node, res)
                if pid is not None:
                    recorder.record_outputs_payload(pid, tagged, label_kind=label_kind)
                    recorder.process_end(pid, state="FINISHED")
                return tagged
            except Exception as exc:
                if pid is not None:
                    recorder.process_end(pid, state="FAILED", error=str(exc))
                raise

        return _node_app

    def _run_subgraph(self, node, sub_ng: NodeGraph, parent_pid: Optional[str]) -> None:
        sub_engine = ParslEngine(
            name=f"{self.name}::{node.name}",
            recorder=self.recorder,
            config=self.config,
            dfk=self._dfk,
        )
        sub_engine.run(sub_ng, parent_pid=parent_pid)

    def _get_active_graph_pid(self) -> Optional[str]:
        return self._graph_pid

    def _ensure_runtime(self):
        if self._dfk is None:
            self._dfk = _ensure_dfk(self.config)

    def run(
        self,
        ng: NodeGraph,
        parent_pid: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute ``ng`` and return resolved graph outputs."""
        self._ensure_runtime()

        order, incoming, _required = _scan_links_topology(ng)

        values: Dict[str, Any] = self._snapshot_builtins(ng)

        graph_pid = self._start_graph_run(ng, parent_pid)
        previous_pid = self._graph_pid
        self._graph_pid = graph_pid

        try:
            for name in order:
                if name in BUILTIN_NODES:
                    continue

                node = ng.nodes[name]

                kw = dict(_collect_literals(node))
                link_kwargs = self._build_link_kwargs(
                    target_name=name,
                    links=incoming.get(name, []),
                    source_map=values,
                )
                kw.update(link_kwargs)
                kw = update_nested_dict_with_special_keys(kw)

                label_kind = "return" if self._is_graph_node(node) else "create"

                app_fn = self._build_node_executor(node, label_kind=label_kind)
                future = app_fn(graph_pid, **kw)
                values[name] = future

            graph_kwargs = self._build_link_kwargs(
                target_name="graph_outputs",
                links=incoming.get("graph_outputs", []),
                source_map=values,
            )
            graph_kwargs = update_nested_dict_with_special_keys(graph_kwargs)
            graph_outputs = self._resolve_app_futures(graph_kwargs)
            return self._finalize_graph_success(ng, graph_pid, graph_outputs)
        except Exception as exc:
            self._record_graph_failure(graph_pid, exc)
            raise
        finally:
            self._graph_pid = previous_pid

    def _resolve_app_futures(self, value: Any) -> Any:
        if AppFuture is not None and isinstance(value, AppFuture):
            return self._resolve_app_futures(value.result())
        if isinstance(value, TaggedValue):
            return value
        if isinstance(value, dict):
            return {k: self._resolve_app_futures(v) for k, v in value.items()}
        return value
