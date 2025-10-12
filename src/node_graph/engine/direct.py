from __future__ import annotations
from typing import Any, Callable, Dict, Optional

from node_graph import NodeGraph
from node_graph.node_graph import BUILTIN_NODES
from node_graph.socket_spec import SocketSpecAPI
from node_graph.utils import clean_socket_reference, tag_socket_value
from .provenance import ProvenanceRecorder

from .utils import (
    _scan_links_topology,
    _merge_multi_links_for_node,
    _collect_literals,
    update_nested_dict_with_special_keys,
    _resolve_tagged_value,
    parse_outputs,
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

    def run(
        self,
        ng: NodeGraph,
        parent_pid: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute ``ng`` and return the graph outputs as plain values."""
        order, incoming, _required = _scan_links_topology(ng)

        # Built-ins: treat as already "available" values
        values: Dict[str, Dict[str, Any]] = {
            "graph_ctx": ng.ctx._collect_values(raw=False),
            "graph_inputs": ng.inputs._collect_values(raw=False),
            "graph_outputs": ng.outputs._collect_values(raw=False),
        }

        graph_pid = self.recorder.process_start(
            task_name=ng.name,
            callable_obj=None,
            flow_run_id=f"direct:{self.name}",
            task_run_id=f"direct:{ng.name}",
            kind="graph",
            parent_pid=parent_pid,
        )
        self.recorder.record_inputs_payload(
            graph_pid, ng.inputs._collect_values(raw=False)
        )

        try:
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

                is_graph = self._is_graph_node(node)
                pid: Optional[str] = None
                if not is_graph:
                    pid = self.recorder.process_start(
                        task_name=name,
                        callable_obj=fn,
                        flow_run_id=f"direct:{self.name}",
                        task_run_id=f"direct:{name}",
                        parent_pid=graph_pid,
                    )
                    self.recorder.record_inputs_payload(pid, kw)

                try:
                    label_kind = "output"
                    raw_kwargs = _resolve_tagged_value(kw)
                    if is_graph and fn is not None:
                        res = self._run_graph_node(node, fn, kw, graph_pid)
                        label_kind = "return"
                    elif fn is None:
                        res = dict(raw_kwargs)
                    else:
                        res = fn(**raw_kwargs)

                    # push to runtime sockets
                    try:
                        res = parse_outputs(res, node.spec.outputs)
                        node.outputs._set_socket_value(res)
                    except Exception:
                        pass
                    tag_socket_value(node.outputs, only_uuid=True)
                    tagged_out = node.outputs._collect_values(raw=False)

                    values[name] = tagged_out

                    if pid is not None:
                        self.recorder.record_outputs_payload(
                            pid, tagged_out, label_kind=label_kind
                        )
                        self.recorder.process_end(pid, state="FINISHED")
                except Exception as e:
                    if pid is not None:
                        self.recorder.process_end(pid, state="FAILED", error=str(e))
                    raise

            graph_links = incoming.get("graph_outputs", [])
            graph_outputs = _merge_multi_links_for_node(
                target_name="graph_outputs",
                links_into_node=graph_links,
                whole_task_future=values,
            )
            graph_outputs = clean_socket_reference(graph_outputs)
            ng.outputs._set_socket_value(graph_outputs)
            graph_outputs = ng.outputs._collect_values(raw=False)
            self.recorder.record_outputs_payload(
                graph_pid,
                graph_outputs,
                label_kind="graph_output",
            )
            self.recorder.process_end(graph_pid, state="FINISHED")
            return _resolve_tagged_value(graph_outputs)
        except Exception as e:
            self.recorder.process_end(graph_pid, state="FAILED", error=str(e))
            raise

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
        self, node, graph_fn: Callable, kwargs: Dict[str, Any], parent_pid: str
    ) -> Dict[str, Any]:
        """
        1) create sub-NodeGraph
        2) call the graph function inside its context (populates subgraph; returns socket-handles)
        3) run subgraph with a nested DirectEngine that REUSES THE SAME recorder
        4) collect the executed subgraph outputs and return them as raw values
        """
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

        DirectEngine(name=f"{self.name}::{node.name}", recorder=self.recorder).run(
            sub_ng, parent_pid=parent_pid
        )

        values = sub_ng.outputs._collect_values(raw=False)
        return values
