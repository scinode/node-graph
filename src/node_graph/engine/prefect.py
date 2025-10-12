from __future__ import annotations
from typing import Any, Callable, Dict, List, Optional
from contextvars import ContextVar
from prefect import flow, task
from node_graph.socket_spec import SocketSpecAPI
from node_graph import NodeGraph
from node_graph.node_graph import BUILTIN_NODES
from .provenance import ProvenanceRecorder
from .utils import (
    _scan_links_topology,
    update_nested_dict_with_special_keys,
    get_nested_dict,
    _collect_literals,
    update_nested_dict,
    parse_outputs,
    _resolve_tagged_value,
)
from node_graph.utils import clean_socket_reference
from prefect.runtime import flow_run, task_run
from prefect.task_runners import ThreadPoolTaskRunner
from prefect.futures import PrefectFuture
from prefect.states import State
from node_graph.utils import tag_socket_value

DEFAULT_OUT = SocketSpecAPI.DEFAULT_OUTPUT_KEY
_GRAPH_PID_CTX = ContextVar("node_graph_prefect_graph_pid", default=None)


def _unwrap_callable(
    node, engine: Optional["PrefectEngine"] = None
) -> Optional[Callable]:
    """Return a real Python callable for a node (or None if no executor)."""
    if getattr(node.spec, "node_type", "").lower() == "graph":
        return _make_graph_wrapper(node, engine)

    exec_obj = getattr(node.spec, "executor", None)
    if not exec_obj:
        return None
    fn = getattr(exec_obj, "callable", None)
    if hasattr(fn, "_callable"):
        fn = getattr(fn, "_callable")
    return fn


def _make_graph_wrapper(node, engine: Optional["PrefectEngine"]):
    """
    Return a callable(**kwargs) that builds a sub-NodeGraph from the graph node's
    function, adapts it to a Prefect subgraph, executes it, and returns a dict
    shaped like the graph node's outputs spec.
    """
    exec_obj = getattr(node.spec, "executor", None)
    graph_fn = getattr(exec_obj, "callable", None)
    if hasattr(graph_fn, "_callable"):
        graph_fn = getattr(graph_fn, "_callable")

    def _graph_runner(**kwargs):
        from node_graph.utils.graph import materialize_graph
        from node_graph import NodeGraph

        sub_ng = materialize_graph(
            graph_fn,
            node.spec.inputs,
            node.spec.outputs,
            node.name,
            NodeGraph,
            args=(),
            kwargs=kwargs,
            var_kwargs={},
        )
        sub_ng.name = f"{node.name}__subgraph"
        sub_engine = PrefectEngine(
            flow_name=f"{node.name}__subgraph",
            recorder=engine.recorder if engine is not None else None,
        )
        sub_engine.run(sub_ng, parent_pid=_GRAPH_PID_CTX.get())

        # Shape outputs to match the graph node's outputs spec
        #    If a returned value is a socket-like handle, read its future from run_map.
        values = sub_ng.outputs._collect_values(raw=False)
        return values

    return _graph_runner


def _make_prefect_task_with_prov_runtime(
    node, engine: "PrefectEngine", label_kind: str
):
    """
    Prefect @task that:
      - starts a provenance process (with runtime run IDs),
      - records *runtime* flattened inputs from kwargs,
      - executes fn(**kwargs) (or passthrough if fn is None),
      - normalizes outputs to dict,
      - records *runtime* flattened outputs,
      - ends the provenance process.
    This supports dynamic namespaces for both inputs and outputs.
    """
    recorder = engine.recorder
    fn = _unwrap_callable(node, engine)
    is_graph = getattr(node.spec, "node_type", "").lower() == "graph"
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
                outputs = dict(kwargs)  # passthrough
                recorder.record_outputs_payload(pid, outputs, label_kind=label_kind)
                recorder.process_end(pid, state="FINISHED")
                return outputs
            except Exception as e:
                recorder.process_end(pid, state="FAILED", error=str(e))
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
            # Record inputs with real, runtime keys (handles dynamic namespaces)
            recorder.record_inputs_payload(pid, kwargs)
        try:
            # get the raw value of the kwargs recursively
            call_kwargs = kwargs if is_graph else _resolve_tagged_value(kwargs)
            res = fn(**call_kwargs)
            res = parse_outputs(res, node.spec.outputs)
            node.outputs._set_socket_value(res)
            tag_socket_value(node.outputs, only_uuid=True)
            res = node.outputs._collect_values(raw=False)
            # Record outputs with real keys (handles dynamic outputs)
            if pid is not None:
                recorder.record_outputs_payload(pid, res, label_kind=label_kind)
                recorder.process_end(pid, state="FINISHED")
            return res
        except Exception as e:
            if pid is not None:
                recorder.process_end(pid, state="FAILED", error=str(e))
            raise
        finally:
            if token is not None:
                _GRAPH_PID_CTX.reset(token)

    return _node_task


@task(name="ng:get_nested")
def _prefect_get_nested(d: Dict[str, Any], dotted: str, default=None):
    return get_nested_dict(d, dotted, default=default)


def _future_link_kwargs(
    target_name: str, incoming: Dict[str, List], all_task_future: Dict[str, Any]
) -> Dict[str, Any]:
    grouped: Dict[str, List] = {}
    for lk in incoming.get(target_name, []):
        grouped.setdefault(lk.to_socket._scoped_name, []).append(lk)

    kwargs: Dict[str, Any] = {}
    for to_sock, lks in grouped.items():
        if len(lks) == 1:
            lk = lks[0]
            from_name = lk.from_node.name
            from_sock = lk.from_socket._scoped_name

            if from_sock == "_wait":
                # handled as dependency, not as an argument
                continue
            elif from_sock == "_outputs":
                # pass the whole upstream dict future straight through
                kwargs[to_sock] = all_task_future[from_name]
            else:
                # defer extraction until runtime → returns a future
                kwargs[to_sock] = _prefect_get_nested.submit(
                    all_task_future[from_name], from_sock, default=None
                )
        else:
            # multiple links → bundle dict of futures
            bundle: Dict[str, Any] = {}
            for lk in lks:
                from_name = lk.from_node.name
                from_sock = lk.from_socket._scoped_name
                if from_sock in ("_wait", "_outputs"):
                    continue
                key = f"{from_name}_{from_sock}"
                bundle[key] = _prefect_get_nested.submit(
                    all_task_future[from_name], from_sock, default=None
                )
            kwargs[to_sock] = bundle
    return kwargs


class PrefectEngine:
    """
    Prefect engine for NodeGraph.
      - Builds a Flow from nodes/links with Kahn topological order.
      - Supports multi-fan-in by bundling into a dict with "{fromNode}_{fromSocket}" keys.
    """

    def __init__(
        self,
        flow_name: str = "node-graph-flow",
        use_analysis: bool = False,
        task_runner=None,
        recorder=None,
    ):
        self.flow_name = flow_name
        self.use_analysis = use_analysis
        self.recorder = recorder or ProvenanceRecorder(flow_name or "node-graph")
        self.task_runner = task_runner or ThreadPoolTaskRunner()

    def to_flow(self, ng: NodeGraph):
        order, incoming, required_out_sockets = _scan_links_topology(ng)

        task_funcs: Dict[str, Callable] = {}
        for name in ng.get_node_names():
            node = ng.nodes[name]
            node_type = getattr(node.spec, "node_type", "") or ""
            label_kind = "return" if node_type.upper() == "GRAPH" else "create"
            task_funcs[name] = _make_prefect_task_with_prov_runtime(
                node, self, label_kind
            )

        @flow(name=self.flow_name, task_runner=self.task_runner)  # <-- concurrency ON
        def adapted_flow():
            literals = {n: _collect_literals(ng.nodes[n]) for n in ng.get_node_names()}

            all_task_future: Dict[str, Any] = {
                "graph_ctx": ng.ctx._collect_values(raw=False),
                "graph_inputs": ng.inputs._collect_values(raw=False),
                "graph_outputs": ng.outputs._collect_values(raw=False),
            }

            for n in order:
                if n in BUILTIN_NODES:
                    continue

                kw = dict(literals[n])

                kw.update(_future_link_kwargs(n, incoming, all_task_future))
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

        graph_pid = self.recorder.process_start(
            ng.name,
            callable_obj=None,
            flow_run_id=f"prefect:{self.flow_name}",
            task_run_id=f"prefect:{ng.name}",
            kind="graph",
            parent_pid=parent_pid,
        )
        self.recorder.record_inputs_payload(
            graph_pid, ng.inputs._collect_values(raw=False)
        )

        token = _GRAPH_PID_CTX.set(graph_pid)
        try:
            state_map = flow_fn()
            resolved = {
                name: self._resolve_state(value) for name, value in state_map.items()
            }
            self._apply_meta_links(ng, resolved)
            graph_outputs = resolved.get("graph_outputs", {}) or {}
            graph_outputs = clean_socket_reference(graph_outputs)
            ng.outputs._set_socket_value(graph_outputs)
            self.recorder.record_outputs_payload(
                graph_pid,
                graph_outputs,
                label_kind="graph_output",
            )
            self.recorder.process_end(graph_pid, state="FINISHED")
            graph_outputs = _resolve_tagged_value(graph_outputs)
            return graph_outputs
        except Exception as e:
            self.recorder.process_end(graph_pid, state="FAILED", error=str(e))
            raise
        finally:
            _GRAPH_PID_CTX.reset(token)

    @staticmethod
    def _resolve_state(value: Any) -> Any:

        if isinstance(value, PrefectFuture):
            value = value.result()
        if isinstance(value, State):
            return value.result()
        return value

    def _apply_meta_links(
        self,
        ng: NodeGraph,
        results: Dict[str, Dict[str, Any]],
    ) -> None:
        """
        Populate graph_ctx and graph_outputs entries using executed node results
        when there are explicit links targeting those built-ins.
        """
        for name in ("graph_ctx", "graph_outputs"):
            value = results.get(name)
            if value is None or not isinstance(value, dict):
                results[name] = {}
        for link in ng.links:
            to_name = link.to_node.name
            if to_name not in {"graph_ctx", "graph_outputs"}:
                continue
            from_name = link.from_node.name
            node_payload = results.get(from_name)
            if not isinstance(node_payload, dict):
                continue
            from_key = link.from_socket._scoped_name
            if from_key == "_outputs":
                payload = node_payload
            else:
                payload = get_nested_dict(node_payload, from_key, default=None)
            to_key = link.to_socket._scoped_name
            results[to_name] = update_nested_dict(results[to_name], to_key, payload)
        if "graph_outputs" in results:
            ng.outputs = results["graph_outputs"]
        if "graph_ctx" in results:
            ng.ctx = results["graph_ctx"]
