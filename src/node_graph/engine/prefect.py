from __future__ import annotations
from typing import Any, Callable, Dict, Optional
from contextvars import ContextVar
from prefect import flow, task
from node_graph import NodeGraph
from node_graph.node_graph import BUILTIN_NODES
from node_graph.socket import TaggedValue
from .base import BaseEngine
from .utils import (
    _scan_links_topology,
    update_nested_dict_with_special_keys,
    get_nested_dict,
    _collect_literals,
    _resolve_tagged_value,
)
from prefect.runtime import flow_run, task_run
from prefect.task_runners import ThreadPoolTaskRunner
from prefect.futures import PrefectFuture
from prefect.states import State

_GRAPH_PID_CTX = ContextVar("node_graph_prefect_graph_pid", default=None)


@task(name="ng:get_nested")
def _prefect_get_nested(d: Dict[str, Any], dotted: str, default=None):
    return get_nested_dict(d, dotted, default=default)


class PrefectEngine(BaseEngine):
    """
    Prefect engine for NodeGraph.
      - Builds a Flow from nodes/links with Kahn topological order.
      - Supports multi-fan-in by bundling into a dict with "{fromNode}_{fromSocket}" keys.
    """

    engine_kind = "prefect"

    def __init__(
        self,
        flow_name: str = "node-graph-flow",
        use_analysis: bool = False,
        task_runner=None,
        recorder=None,
    ):
        super().__init__(flow_name, recorder)
        self.flow_name = flow_name
        self.use_analysis = use_analysis
        self.task_runner = task_runner or ThreadPoolTaskRunner()

    def _link_socket_value(
        self, from_name: str, from_socket: str, source_map: Dict[str, Any]
    ) -> Any:
        upstream = source_map[from_name]
        if isinstance(upstream, PrefectFuture):
            return _prefect_get_nested.submit(upstream, from_socket, default=None)
        return super()._link_socket_value(from_name, from_socket, source_map)

    def _build_node_executor(self, node, label_kind: str):
        recorder = self.recorder
        fn = self._unwrap_callable(node)
        is_graph = self._is_graph_node(node)

        if fn is None:

            @task(name=f"node:{node.name}")
            def _noop(**kwargs):
                fr_id = flow_run.get_id()
                tr_id = task_run.get_id()
                parent_pid = _GRAPH_PID_CTX.get()
                pid = recorder.process_start(
                    node.name, None, fr_id, tr_id, parent_pid=parent_pid
                )
                token = _GRAPH_PID_CTX.set(pid)
                recorder.record_inputs_payload(pid, kwargs)
                try:
                    outputs = dict(kwargs)
                    recorder.record_outputs_payload(pid, outputs, label_kind=label_kind)
                    recorder.process_end(pid, state="FINISHED")
                    return outputs
                except Exception as exc:
                    recorder.process_end(pid, state="FAILED", error=str(exc))
                    raise
                finally:
                    _GRAPH_PID_CTX.reset(token)

            return _noop

        @task(name=f"node:{node.name}")
        def _node_task(**kwargs):
            fr_id = flow_run.get_id()
            tr_id = task_run.get_id()
            parent_pid = _GRAPH_PID_CTX.get()
            pid: Optional[str] = None
            token = None
            if not is_graph:
                pid = recorder.process_start(
                    node.name, fn, fr_id, tr_id, parent_pid=parent_pid
                )
                token = _GRAPH_PID_CTX.set(pid)
                recorder.record_inputs_payload(pid, kwargs)
            try:
                call_kwargs = kwargs if is_graph else _resolve_tagged_value(kwargs)
                res = fn(**call_kwargs)
                res = self._normalize_outputs(node, res)
                if pid is not None:
                    recorder.record_outputs_payload(pid, res, label_kind=label_kind)
                    recorder.process_end(pid, state="FINISHED")
                return res
            except Exception as exc:
                if pid is not None:
                    recorder.process_end(pid, state="FAILED", error=str(exc))
                raise
            finally:
                if token is not None:
                    _GRAPH_PID_CTX.reset(token)

        return _node_task

    def _run_subgraph(self, node, sub_ng: NodeGraph, parent_pid: Optional[str]) -> None:
        sub_engine = PrefectEngine(
            flow_name=f"{node.name}__subgraph",
            recorder=self.recorder,
            task_runner=self.task_runner,
        )
        sub_engine.run(sub_ng, parent_pid=parent_pid)

    def _get_active_graph_pid(self) -> Optional[str]:
        return _GRAPH_PID_CTX.get()

    def to_flow(self, ng: NodeGraph):
        order, incoming, required_out_sockets = _scan_links_topology(ng)

        task_funcs: Dict[str, Callable] = {}
        for name in ng.get_node_names():
            node = ng.nodes[name]
            node_type = getattr(node.spec, "node_type", "") or ""
            label_kind = "return" if node_type.upper() == "GRAPH" else "create"
            task_funcs[name] = self._build_node_executor(node, label_kind)

        @flow(name=self.flow_name, task_runner=self.task_runner)  # <-- concurrency ON
        def adapted_flow():
            literals = {n: _collect_literals(ng.nodes[n]) for n in ng.get_node_names()}

            all_task_future: Dict[str, Any] = self._snapshot_builtins(ng)

            for n in order:
                if n in BUILTIN_NODES:
                    continue

                kw = dict(literals[n])

                kw.update(
                    self._build_link_kwargs(
                        target_name=n,
                        links=incoming.get(n, []),
                        source_map=all_task_future,
                    )
                )
                kw = update_nested_dict_with_special_keys(kw)

                # collect explicit wait deps from _wait edges
                wait_deps = []
                for lk in incoming.get(n, []):
                    if lk.from_socket._scoped_name == "_wait":
                        # depend on the WHOLE upstream task dict future
                        up = all_task_future.get(lk.from_node.name)
                        if up is not None:
                            wait_deps.append(up)

                # schedule with explicit dependencies (does not block others)
                if wait_deps:
                    node_dict_future = task_funcs[n].submit(**kw, wait_for=wait_deps)
                else:
                    node_dict_future = task_funcs[n].submit(**kw)
                all_task_future[n] = node_dict_future

            return all_task_future

        return adapted_flow

    def run(self, ng: NodeGraph, parent_pid: Optional[str] = None) -> Dict[str, Any]:
        """Build the flow and execute it synchronously; returns mapping of Prefect futures."""
        flow_fn = self.to_flow(ng)
        _, incoming, _ = _scan_links_topology(ng)

        graph_pid = self._start_graph_run(ng, parent_pid)

        token = _GRAPH_PID_CTX.set(graph_pid)
        try:
            state_map = flow_fn()
            resolved = {
                name: self._resolve_state(value) for name, value in state_map.items()
            }
            graph_outputs = self._build_link_kwargs(
                target_name="graph_outputs",
                links=incoming.get("graph_outputs", []),
                source_map=resolved,
            )
            return self._finalize_graph_success(ng, graph_pid, graph_outputs)
        except Exception as e:
            self._record_graph_failure(graph_pid, e)
            raise
        finally:
            _GRAPH_PID_CTX.reset(token)

    def _resolve_state(self, value: Any) -> Any:

        if isinstance(value, PrefectFuture):
            value = value.result()
        if isinstance(value, State):
            return value.result()
        if isinstance(value, TaggedValue):
            return value
        if isinstance(value, dict):
            return {k: self._resolve_state(v) for k, v in value.items()}
        return value
