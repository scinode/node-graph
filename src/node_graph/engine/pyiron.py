from __future__ import annotations

import os
import re
import shutil
import tempfile
from typing import Any, Callable, Dict, Optional
from uuid import uuid4

from node_graph import NodeGraph
from node_graph.node_graph import BUILTIN_NODES

from .base import BaseEngine
from .provenance import ProvenanceRecorder
from .utils import (
    _collect_literals,
    _resolve_tagged_value,
    _scan_links_topology,
    get_nested_dict,
    update_nested_dict_with_special_keys,
)

from pyiron_base import Project


_JOB_NAME_SANITIZE_RE = re.compile(r"[^0-9A-Za-z_]+")


def _sanitize_job_name(*parts: str) -> str:
    raw = "_".join(parts)
    return _JOB_NAME_SANITIZE_RE.sub("_", raw)


class PyironEngine(BaseEngine):
    """Execute NodeGraphs using wrapped pyiron python functions while recording provenance."""

    engine_kind = "pyiron"

    def __init__(
        self,
        name: str = "pyiron-flow",
        *,
        recorder: Optional[ProvenanceRecorder] = None,
        project: Optional["Project"] = None,
        project_path: Optional[str] = None,
        cleanup_project: bool = False,
        auto_cleanup_jobs: bool = True,
    ):

        super().__init__(name, recorder)

        self._graph_pid: Optional[str] = None
        self._auto_cleanup_jobs = auto_cleanup_jobs

        if project is not None:
            self.project = project
            self._owns_project = False
            self._project_dir: Optional[str] = None
        else:
            self._owns_project = True
            if project_path is None:
                project_path = tempfile.mkdtemp(prefix="node_graph_pyiron_")
            else:
                os.makedirs(project_path, exist_ok=True)
            self._project_dir = project_path
            self.project = Project(project_path)

        self._cleanup_project = cleanup_project and self._owns_project

    def __del__(self):
        if getattr(self, "_cleanup_project", False) and getattr(
            self, "_project_dir", None
        ):
            shutil.rmtree(self._project_dir, ignore_errors=True)

    def _link_socket_value(
        self, from_name: str, from_socket: str, source_map: Dict[str, Any]
    ) -> Any:
        upstream = source_map[from_name]
        if isinstance(upstream, dict):
            return get_nested_dict(upstream, from_socket, default=None)
        return super()._link_socket_value(from_name, from_socket, source_map)

    def _build_node_executor(self, node, label_kind: str):
        recorder = self.recorder
        fn = self._unwrap_callable(node)
        is_graph = self._is_graph_node(node)

        job_name = _sanitize_job_name("node_pyiron", self.name, node.name)

        if fn is None:

            def _noop_job(parent_pid: Optional[str], **kwargs: Any) -> Dict[str, Any]:
                pid = recorder.process_start(
                    node.name,
                    None,
                    flow_run_id=f"pyiron:{self.name}",
                    task_run_id=f"pyiron:{node.name}",
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

        def _node_job(parent_pid: Optional[str], **kwargs: Any) -> Dict[str, Any]:
            pid: Optional[str] = None
            if not is_graph:
                pid = recorder.process_start(
                    node.name,
                    fn,
                    flow_run_id=f"pyiron:{self.name}",
                    task_run_id=f"pyiron:{node.name}",
                    parent_pid=parent_pid,
                )
                recorder.record_inputs_payload(pid, kwargs)
            try:
                call_kwargs = kwargs if is_graph else _resolve_tagged_value(kwargs)
                if is_graph:
                    res = fn(**call_kwargs)
                else:
                    res = self._execute_pyiron_function(job_name, fn, call_kwargs)
                tagged = self._normalize_outputs(node, res, strict=False)
                if pid is not None:
                    recorder.record_outputs_payload(pid, tagged, label_kind=label_kind)
                    recorder.process_end(pid, state="FINISHED")
                return tagged
            except Exception as exc:
                if pid is not None:
                    recorder.process_end(pid, state="FAILED", error=str(exc))
                raise

        return _node_job

    def _execute_pyiron_function(
        self,
        job_name: str,
        fn: Callable[..., Any],
        call_kwargs: Dict[str, Any],
    ) -> Any:
        job = self.project.wrap_python_function(
            fn,
            job_name=job_name,
            automatically_rename=True,
            execute_job=False,
        )
        sanitized_kwargs = _resolve_tagged_value(call_kwargs)
        for key, value in sanitized_kwargs.items():
            job.input[key] = value
        job.run()
        output = getattr(job, "output", None)
        result: Any = None
        if output is not None:
            if isinstance(output, dict):
                result = output.get("result", output)
            else:
                try:
                    result = output["result"]
                except Exception:
                    if hasattr(output, "to_builtin"):
                        result = output.to_builtin()
                    else:
                        result = output
        if self._auto_cleanup_jobs:
            try:
                job.remove()
            except Exception:
                pass
        return result

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

        try:
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

                tagged_outputs = executor(graph_pid, **kw)
                values[name] = tagged_outputs

            graph_outputs = self._build_link_kwargs(
                target_name="graph_outputs",
                links=incoming.get("graph_outputs", []),
                source_map=values,
            )
            graph_outputs = update_nested_dict_with_special_keys(graph_outputs)
            return self._finalize_graph_success(ng, graph_pid, graph_outputs)
        except Exception as exc:
            self._record_graph_failure(graph_pid, exc)
            raise
        finally:
            self._graph_pid = previous_pid

    def _run_subgraph(self, node, sub_ng: NodeGraph, parent_pid: Optional[str]) -> None:
        sub_project = self.project.create_group(f"{node.name}_sub_{uuid4().hex[:8]}")
        sub_engine = PyironEngine(
            name=f"{self.name}::{node.name}",
            recorder=self.recorder,
            project=sub_project,
            cleanup_project=False,
            auto_cleanup_jobs=self._auto_cleanup_jobs,
        )
        sub_engine.run(sub_ng, parent_pid=parent_pid)

    def _get_active_graph_pid(self) -> Optional[str]:
        return self._graph_pid
