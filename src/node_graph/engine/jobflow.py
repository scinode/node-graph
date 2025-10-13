from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from node_graph import NodeGraph
from node_graph.node_graph import BUILTIN_NODES
from node_graph.socket import TaggedValue

from .base import BaseEngine
from .provenance import ProvenanceRecorder
from .utils import (
    _collect_literals,
    _resolve_tagged_value,
    _scan_links_topology,
    update_nested_dict_with_special_keys,
    get_nested_dict,
)

from jobflow import Flow, job, run_locally  # type: ignore
from jobflow.core.job import Job  # type: ignore
from jobflow.core.reference import OutputReference  # type: ignore

_GRAPH_OUTPUTS_KEY = "graph_outputs"


@job(name="jobflow_bundle")
def _jobflow_bundle(**kwargs: Any) -> Dict[str, Any]:
    return kwargs


@job(name="jobflow_get_nested")
def _jobflow_get_nested(d: Dict[str, Any], dotted: str, default=None):
    return get_nested_dict(d, dotted, default=default)


class JobflowEngine(BaseEngine):
    """Execute NodeGraphs using jobflow while recording provenance."""

    engine_kind = "jobflow"

    def __init__(
        self,
        name: str = "jobflow-flow",
        *,
        recorder: Optional[ProvenanceRecorder] = None,
    ):
        super().__init__(name, recorder)
        self._graph_pid: Optional[str] = None
        self._link_jobs: Dict[Tuple[str, str], Job] = {}

    def _link_socket_value(
        self, from_name: str, from_socket: str, source_map: Dict[str, Any]
    ) -> Any:
        upstream = source_map[from_name]
        if isinstance(upstream, Job):
            upstream = upstream.output
        if isinstance(upstream, OutputReference):
            key = (from_name, from_socket)
            nested_job = self._link_jobs.get(key)
            if nested_job is None:
                nested_job = _jobflow_get_nested(upstream, from_socket, default=None)
                self._link_jobs[key] = nested_job
            return nested_job.output
        if isinstance(upstream, dict):
            return get_nested_dict(upstream, from_socket, default=None)
        return super()._link_socket_value(from_name, from_socket, source_map)

    def _link_bundle(self, payload: Dict[str, Any]) -> Any:
        return _jobflow_bundle(**payload)

    def _build_node_executor(self, node, label_kind: str):
        recorder = self.recorder
        fn = self._unwrap_callable(node)
        is_graph = self._is_graph_node(node)

        job_name = f"node_jobflow_{self.name}_{node.name}"

        if fn is None:

            @job(name=job_name)
            def _noop_job(parent_pid: Optional[str], **kwargs: Any) -> Dict[str, Any]:
                pid = recorder.process_start(
                    node.name,
                    None,
                    flow_run_id=f"jobflow:{self.name}",
                    task_run_id=f"jobflow:{node.name}",
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

            return _noop_job

        @job(name=job_name)
        def _node_job(parent_pid: Optional[str], **kwargs: Any) -> Dict[str, Any]:
            pid: Optional[str] = None
            if not is_graph:
                pid = recorder.process_start(
                    node.name,
                    fn,
                    flow_run_id=f"jobflow:{self.name}",
                    task_run_id=f"jobflow:{node.name}",
                    parent_pid=parent_pid,
                )
                recorder.record_inputs_payload(pid, kwargs)
            try:
                call_kwargs = kwargs if is_graph else _resolve_tagged_value(kwargs)
                res = fn(**call_kwargs)
                tagged = self._normalize_outputs(node, res, strict=False)
                resolved = _resolve_tagged_value(tagged)
                if pid is not None:
                    recorder.record_outputs_payload(pid, tagged, label_kind=label_kind)
                    recorder.process_end(pid, state="FINISHED")
                return resolved
            except Exception as exc:
                if pid is not None:
                    recorder.process_end(pid, state="FAILED", error=str(exc))
                raise

        return _node_job

    def run(
        self,
        ng: NodeGraph,
        parent_pid: Optional[str] = None,
    ) -> Dict[str, Any]:
        order, incoming, _required = _scan_links_topology(ng)
        values: Dict[str, Any] = self._snapshot_builtins(ng)

        graph_pid = self._start_graph_run(ng, parent_pid)
        previous_pid = self._graph_pid
        self._graph_pid = graph_pid

        job_map: Dict[str, Job] = {}

        try:
            self._link_jobs = {}
            for name in order:
                if name in BUILTIN_NODES:
                    continue

                node = ng.nodes[name]
                label_kind = "return" if self._is_graph_node(node) else "output"
                executor = self._build_node_executor(node, label_kind=label_kind)

                kw = dict(_collect_literals(node))
                link_kwargs = self._build_link_kwargs(
                    target_name=name,
                    links=incoming.get(name, []),
                    source_map=values,
                )
                kw.update(link_kwargs)
                kw = update_nested_dict_with_special_keys(kw)

                job_obj = executor(graph_pid, **kw)
                job_map[name] = job_obj
                values[name] = job_obj

            graph_kwargs = self._build_link_kwargs(
                target_name="graph_outputs",
                links=incoming.get("graph_outputs", []),
                source_map=values,
            )
            graph_kwargs = update_nested_dict_with_special_keys(graph_kwargs)

            terminal_job: Optional[Job] = None
            if graph_kwargs:
                terminal_job = _jobflow_bundle(**graph_kwargs)
                job_map[_GRAPH_OUTPUTS_KEY] = terminal_job

            flow_jobs = list(job_map.values())
            if self._link_jobs:
                flow_jobs.extend(self._link_jobs.values())

            flow = Flow(flow_jobs, name=self.engine_kind)
            flow_result = run_locally(flow)
            result_map = getattr(flow_result, "results", flow_result)

            graph_outputs: Any = {}
            if terminal_job is not None:
                terminal_results = result_map.get(str(terminal_job.uuid), {})
                if isinstance(terminal_results, dict):
                    terminal_response = terminal_results.get(
                        getattr(terminal_job, "index", 1), None
                    )
                    if terminal_response is None and terminal_results:
                        terminal_response = next(iter(terminal_results.values()))
                else:
                    terminal_response = terminal_results

                if hasattr(terminal_response, "output"):
                    graph_outputs = terminal_response.output
                elif terminal_response is None:
                    graph_outputs = {}
                else:
                    graph_outputs = terminal_response

            wrapped_outputs = self._wrap_with_tags(graph_outputs)
            return self._finalize_graph_success(ng, graph_pid, wrapped_outputs)
        except Exception as exc:
            self._record_graph_failure(graph_pid, exc)
            raise
        finally:
            self._graph_pid = previous_pid
            self._link_jobs = {}

    def _run_subgraph(self, node, sub_ng: NodeGraph, parent_pid: Optional[str]) -> None:
        sub_engine = JobflowEngine(
            name=f"{self.name}::{node.name}",
            recorder=self.recorder,
        )
        sub_engine.run(sub_ng, parent_pid=parent_pid)

    def _get_active_graph_pid(self) -> Optional[str]:
        return self._graph_pid

    def _wrap_with_tags(self, value: Any) -> Any:
        if isinstance(value, TaggedValue):
            return value
        if isinstance(value, dict):
            return {k: self._wrap_with_tags(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self._wrap_with_tags(v) for v in value]
        if isinstance(value, tuple):
            return tuple(self._wrap_with_tags(v) for v in value)
        if value is None:
            return None
        return TaggedValue(value)
