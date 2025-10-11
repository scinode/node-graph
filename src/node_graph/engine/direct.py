from __future__ import annotations
from typing import Any, Callable, Dict, Optional

from node_graph import NodeGraph
from node_graph.node_graph import BUILTIN_NODES
from node_graph.socket_spec import SocketSpecAPI
from .provenance import ProvenanceRecorder

from .utils import (
    _scan_links_topology,
    _merge_multi_links_for_node,
    _collect_literals,
    update_nested_dict_with_special_keys,
)

DEFAULT_OUT = SocketSpecAPI.DEFAULT_OUTPUT_KEY


class DirectEngine:
    """
    Sync, dependency-free runner with provenance:

    - @node: calls the underlying python function, normalizes to {result: ...}
    - @node.graph: builds & runs a sub-NodeGraph, resolves returned socket-handles to values
    - Provenance: records runtime *flattened* inputs & outputs around each node run
    - Link semantics from utils: _wait, _outputs, and multi-fan-in bundling
    """

    def __init__(
        self, name: str = "direct-flow", recorder: Optional[ProvenanceRecorder] = None
    ):
        self.name = name
        # Share the same recorder across nested subgraphs so an entire run is in one DAG
        self.recorder = recorder or ProvenanceRecorder(self.name)

    def run(self, ng: NodeGraph) -> Dict[str, Dict[str, Any]]:
        """Execute `ng` and return:"""
        order, incoming, _required = _scan_links_topology(ng)

        # Built-ins: treat as already "available" values
        values: Dict[str, Dict[str, Any]] = {
            "graph_ctx": ng.ctx._value,
            "graph_inputs": ng.inputs._value,
            "graph_outputs": ng.outputs._value,
        }

        for name in order:
            if name in BUILTIN_NODES:
                continue

            node = ng.nodes[name]
            fn = self._unwrap_callable(node)

            kw = dict(_collect_literals(node))
            link_kwargs = _merge_multi_links_for_node(
                target_name=name,
                links_into_node=incoming.get(name, []),
                whole_task_future=values,
            )
            kw.update(link_kwargs)
            kw = update_nested_dict_with_special_keys(kw)

            pid = self.recorder.process_start(
                task_name=name,
                callable_obj=fn,
                flow_run_id=f"direct:{self.name}",
                task_run_id=f"direct:{name}",
            )
            self.recorder.record_inputs_payload(pid, kw)

            try:
                label_kind = "output"
                if self._is_graph_node(node) and fn is not None:
                    out = self._run_graph_node(node, fn, kw)
                    label_kind = "return"
                elif fn is None:
                    out = dict(kw)
                else:
                    res = fn(**kw)
                    out = res if isinstance(res, dict) else {DEFAULT_OUT: res}

                # push to runtime sockets
                try:
                    node.outputs._set_socket_value(out)
                except Exception:
                    pass

                values[name] = out

                self.recorder.record_outputs_payload(pid, out, label_kind=label_kind)
                self.recorder.process_end(pid, state="FINISHED")
            except Exception as e:
                self.recorder.process_end(pid, state="FAILED", error=str(e))
                raise

        return values

    @staticmethod
    def _unwrap_callable(node) -> Optional[Callable]:
        exec_obj = getattr(node.spec, "executor", None)
        if not exec_obj:
            return None
        fn = getattr(exec_obj, "callable", None)
        if hasattr(fn, "_callable"):
            fn = getattr(fn, "_callable")
        return fn

    @staticmethod
    def _is_graph_node(node) -> bool:
        return getattr(node.spec, "node_type", "").lower() == "graph"  #

    def _run_graph_node(
        self, node, graph_fn: Callable, kwargs: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        1) create sub-NodeGraph
        2) call the graph function inside its context (populates subgraph; returns socket-handles)
        3) run subgraph with a nested DirectEngine that REUSES THE SAME recorder
        4) resolve returned handles to *values* from the executed subgraph
        """
        sub_ng = NodeGraph(name=f"{node.name}__subgraph")
        with sub_ng:
            returned = graph_fn(**kwargs) or {}

        # Reuse the same recorder so subgraph nodes become part of one provenance DAG
        sub_res = DirectEngine(
            name=f"{self.name}::{node.name}", recorder=self.recorder
        ).run(sub_ng)

        resolved: Dict[str, Any] = {}
        for k, v in returned.items():
            if hasattr(v, "_node") and hasattr(v, "_scoped_name"):
                src = getattr(v._node, "name", None)
                sock = v._scoped_name
                if src is None:
                    raise RuntimeError(f"Unresolvable socket for graph output '{k}'")
                resolved[k] = self._get_nested(sub_res[src], sock)
            else:
                resolved[k] = v
        return resolved

    @staticmethod
    def _get_nested(d: Dict[str, Any], dotted: str, default=None):
        cur = d
        for part in dotted.split("."):
            if not isinstance(cur, dict) or part not in cur:
                return default
            cur = cur[part]
        return cur
