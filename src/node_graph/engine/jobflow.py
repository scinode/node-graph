from __future__ import annotations

from collections import defaultdict
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
        self._input_metadata: Dict[str, Any] = {}

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

        job_name = f"{node.name}"

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
                tagged_inputs = self._prepare_tagged_inputs(node.name, kwargs)
                recorder.record_inputs_payload(pid, tagged_inputs)
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
            tagged_inputs = self._prepare_tagged_inputs(node.name, kwargs)
            if not is_graph:
                pid = recorder.process_start(
                    node.name,
                    fn,
                    flow_run_id=f"jobflow:{self.name}",
                    task_run_id=f"jobflow:{node.name}",
                    parent_pid=parent_pid,
                )
                recorder.record_inputs_payload(pid, tagged_inputs)
            try:
                call_kwargs = tagged_inputs if is_graph else kwargs
                res = fn(**call_kwargs)
                tagged = self._normalize_outputs(node, res, strict=False)
                resolved = _resolve_tagged_value(tagged)
                if pid is not None:
                    recorder.record_outputs_payload(pid, tagged, label_kind=label_kind)
                    recorder.process_end(pid, state="FINISHED")
                else:
                    self.recorder._latest_outputs_by_task[node.name] = tagged
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
        self.recorder._latest_outputs_by_task = values

        graph_pid = self._start_graph_run(ng, parent_pid)
        previous_pid = self._graph_pid
        self._graph_pid = graph_pid

        job_map: Dict[str, Job] = {}

        try:
            self._link_jobs = {}
            self._input_metadata = {}
            for name in order:
                if name in BUILTIN_NODES:
                    continue

                node = ng.nodes[name]
                label_kind = "return" if self._is_graph_node(node) else "create"
                executor = self._build_node_executor(node, label_kind=label_kind)

                kw = dict(_collect_literals(node))
                literal_meta = {k: "literal" for k in kw.keys()}
                link_kwargs, link_meta = self._compile_link_payloads(
                    target_name=name,
                    links=incoming.get(name, []),
                    source_map=values,
                )
                kw.update(link_kwargs)
                input_meta = {**literal_meta, **link_meta}
                kw = update_nested_dict_with_special_keys(kw)
                input_meta = update_nested_dict_with_special_keys(input_meta)
                self._input_metadata[name] = input_meta

                job_obj = executor(graph_pid, **kw)
                job_map[name] = job_obj
                values[name] = job_obj

            flow_jobs = list(job_map.values())
            if self._link_jobs:
                flow_jobs.extend(self._link_jobs.values())

            flow = Flow(flow_jobs, name=self.engine_kind)
            run_locally(flow)
            graph_outputs = self._build_link_kwargs(
                target_name="graph_outputs",
                links=incoming.get("graph_outputs", []),
                source_map=self.recorder._latest_outputs_by_task,
            )
            graph_outputs = update_nested_dict_with_special_keys(graph_outputs)
            return self._finalize_graph_success(ng, graph_pid, graph_outputs)
        except Exception as exc:
            self._record_graph_failure(graph_pid, exc)
            raise
        finally:
            self._graph_pid = previous_pid
            self._link_jobs = {}
            self._input_metadata = {}

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

    def _compile_link_payloads(
        self,
        target_name: str,
        links,
        source_map: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        grouped = defaultdict(list)
        for lk in links:
            if lk.to_node.name == target_name:
                grouped[lk.to_socket._scoped_name].append(lk)

        payloads: Dict[str, Any] = {}
        metadata: Dict[str, Any] = {}
        for to_sock, lks in grouped.items():
            active_links = [lk for lk in lks if lk.from_socket._scoped_name != "_wait"]
            if not active_links:
                continue

            if len(active_links) == 1:
                lk = active_links[0]
                from_name = lk.from_node.name
                from_sock = lk.from_socket._scoped_name
                if from_sock == "_outputs":
                    payloads[to_sock] = self._link_whole_output(from_name, source_map)
                    metadata[to_sock] = ("whole", from_name)
                else:
                    payloads[to_sock] = self._link_socket_value(
                        from_name, from_sock, source_map
                    )
                    metadata[to_sock] = ("socket", from_name, from_sock)
                continue

            bundle_payload: Dict[str, Any] = {}
            for lk in active_links:
                from_name = lk.from_node.name
                from_sock = lk.from_socket._scoped_name
                if from_sock in ("_wait", "_outputs"):
                    continue
                key = f"{from_name}_{from_sock}"
                bundle_payload[key] = self._link_socket_value(
                    from_name, from_sock, source_map
                )
            if bundle_payload:
                payloads[to_sock] = self._link_bundle(bundle_payload)

        return payloads, metadata

    def _prepare_tagged_inputs(
        self,
        node_name: str,
        runtime_kwargs: Dict[str, Any],
    ) -> Dict[str, Any]:
        metadata = self._input_metadata.get(node_name, {})
        return self._apply_input_metadata(metadata, runtime_kwargs)

    def _apply_input_metadata(self, meta: Any, value: Any) -> Any:
        if isinstance(meta, dict) and isinstance(value, dict):
            return {
                key: self._apply_input_metadata(meta.get(key, "literal"), value[key])
                for key in value
            }

        if meta == "literal":
            return (
                value if isinstance(value, TaggedValue) else self._wrap_with_tags(value)
            )

        if isinstance(meta, tuple):
            kind = meta[0]
            if kind == "socket":
                _, from_name, from_socket = meta
                tagged = self._lookup_tagged_output(from_name, from_socket)
                if tagged is not None:
                    return tagged
                return (
                    value
                    if isinstance(value, TaggedValue)
                    else self._wrap_with_tags(value)
                )
            if kind == "whole":
                _, from_name = meta
                tagged = self.recorder._latest_outputs_by_task.get(from_name)
                if tagged is not None:
                    return tagged
                return (
                    value
                    if isinstance(value, TaggedValue)
                    else self._wrap_with_tags(value)
                )

        return value if isinstance(value, TaggedValue) else self._wrap_with_tags(value)

    def _lookup_tagged_output(
        self,
        from_name: str,
        from_socket: str,
    ) -> Any:
        outputs = self.recorder._latest_outputs_by_task.get(from_name)
        if outputs is None:
            return None
        if from_socket == "_outputs":
            return outputs
        return get_nested_dict(outputs, from_socket, default=None)
