from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from node_graph import NodeGraph
from node_graph.node_graph import BUILTIN_NODES
from node_graph.socket_spec import SocketSpecAPI
from node_graph.utils import clean_socket_reference, tag_socket_value
from node_graph.socket import TaggedValue
from .provenance import ProvenanceRecorder
from .utils import (
    _collect_literals,
    _resolve_tagged_value,
    _scan_links_topology,
    parse_outputs,
    update_nested_dict_with_special_keys,
)

import parsl
from parsl import load
from parsl.app.app import AppFuture, python_app
from parsl.config import Config
from parsl.executors.threads import ThreadPoolExecutor


DEFAULT_OUT = SocketSpecAPI.DEFAULT_OUTPUT_KEY


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


def _parsl_link_kwargs(
    target_name: str,
    incoming,
    future_map: Dict[str, Any],
) -> Dict[str, Any]:
    grouped: Dict[str, List] = {}
    for lk in incoming.get(target_name, []):
        grouped.setdefault(lk.to_socket._scoped_name, []).append(lk)

    kwargs: Dict[str, Any] = {}
    for to_sock, links in grouped.items():
        if len(links) == 1:
            lk = links[0]
            from_name = lk.from_node.name
            from_sock = lk.from_socket._scoped_name

            if from_sock == "_wait":
                continue
            if from_sock == "_outputs":
                kwargs[to_sock] = future_map[from_name]
            else:
                kwargs[to_sock] = _parsl_get_nested(
                    future_map[from_name], from_sock, default=None
                )
        else:
            bundle_kwargs: Dict[str, Any] = {}
            for lk in links:
                from_name = lk.from_node.name
                from_sock = lk.from_socket._scoped_name
                if from_sock in ("_wait", "_outputs"):
                    continue
                key = f"{from_name}_{from_sock}"
                bundle_kwargs[key] = _parsl_get_nested(
                    future_map[from_name], from_sock, default=None
                )
            kwargs[to_sock] = _parsl_bundle(**bundle_kwargs)
    return kwargs


def _unwrap_callable(node, engine: Optional["ParslEngine"]) -> Optional[Callable]:
    if getattr(node.spec, "node_type", "").lower() == "graph":
        return _make_graph_wrapper(node, engine)

    exec_obj = getattr(node.spec, "executor", None)
    if not exec_obj:
        return None
    fn = getattr(exec_obj, "callable", None)
    if hasattr(fn, "_callable"):
        fn = getattr(fn, "_callable")
    return fn


def _make_graph_wrapper(node, engine: Optional["ParslEngine"]) -> Callable:
    exec_obj = getattr(node.spec, "executor", None)
    graph_fn = getattr(exec_obj, "callable", None)
    if hasattr(graph_fn, "_callable"):
        graph_fn = getattr(graph_fn, "_callable")

    def _graph_runner(**kwargs):
        from node_graph.utils.graph import materialize_graph

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
        sub_engine = ParslEngine(
            name=f"{engine.name}::{node.name}" if engine else node.name,
            recorder=engine.recorder if engine is not None else None,
            config=engine.config if engine is not None else None,
            dfk=engine._dfk if engine is not None else None,
        )
        sub_engine.run(sub_ng, parent_pid=engine._graph_pid if engine else None)
        values = sub_ng.outputs._collect_values(raw=False)
        return values

    return _graph_runner


class ParslEngine:
    """
    Run NodeGraphs using Parsl python apps while recording provenance.
    """

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
        self.name = name
        self.recorder = recorder or ProvenanceRecorder(self.name)
        self.config = config or _default_config()
        self._dfk = dfk
        self._graph_pid: Optional[str] = None

    @staticmethod
    def _is_graph_node(node) -> bool:
        return getattr(node.spec, "node_type", "").lower() == "graph"

    def _make_parsl_app(self, node, label_kind: str):
        fn = _unwrap_callable(node, self)
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
                res = parse_outputs(res, node.spec.outputs)
                node.outputs._set_socket_value(res)
                tag_socket_value(node.outputs, only_uuid=True)
                tagged = node.outputs._collect_values(raw=False)
                if pid is not None:
                    recorder.record_outputs_payload(pid, tagged, label_kind=label_kind)
                    recorder.process_end(pid, state="FINISHED")
                return tagged
            except Exception as exc:
                if pid is not None:
                    recorder.process_end(pid, state="FAILED", error=str(exc))
                raise

        return _node_app

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

        values: Dict[str, Any] = {
            "graph_ctx": ng.ctx._collect_values(raw=False),
            "graph_inputs": ng.inputs._collect_values(raw=False),
            "graph_outputs": ng.outputs._collect_values(raw=False),
        }

        graph_pid = self.recorder.process_start(
            task_name=ng.name,
            callable_obj=None,
            flow_run_id=f"parsl:{self.name}",
            task_run_id=f"parsl:{ng.name}",
            kind="graph",
            parent_pid=parent_pid,
        )
        self._graph_pid = graph_pid
        self.recorder.record_inputs_payload(
            graph_pid, ng.inputs._collect_values(raw=False)
        )

        try:
            for name in order:
                if name in BUILTIN_NODES:
                    continue

                node = ng.nodes[name]

                kw = dict(_collect_literals(node))
                link_kwargs = _parsl_link_kwargs(name, incoming, values)
                kw.update(link_kwargs)
                kw = update_nested_dict_with_special_keys(kw)

                label_kind = "output"
                if self._is_graph_node(node):
                    label_kind = "return"

                app_fn = self._make_parsl_app(node, label_kind=label_kind)
                future = app_fn(graph_pid, **kw)
                values[name] = future

            graph_kwargs = _parsl_link_kwargs("graph_outputs", incoming, values)
            graph_kwargs = update_nested_dict_with_special_keys(graph_kwargs)
            graph_outputs = self._resolve_app_futures(graph_kwargs)
            graph_outputs = clean_socket_reference(graph_outputs)
            ng.outputs._set_socket_value(graph_outputs)

            self.recorder.record_outputs_payload(
                graph_pid,
                graph_outputs,
                label_kind="graph_output",
            )
            self.recorder.process_end(graph_pid, state="FINISHED")
            return _resolve_tagged_value(graph_outputs)
        except Exception as exc:
            self.recorder.process_end(graph_pid, state="FAILED", error=str(exc))
            raise
        finally:
            self._graph_pid = None

    def _resolve_app_futures(self, value: Any) -> Any:
        if AppFuture is not None and isinstance(value, AppFuture):
            return self._resolve_app_futures(value.result())
        if isinstance(value, TaggedValue):
            return value
        if isinstance(value, dict):
            return {k: self._resolve_app_futures(v) for k, v in value.items()}
        return value
