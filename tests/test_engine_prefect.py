import pytest

pytest.importorskip("prefect")
from node_graph import NodeGraph, node
from node_graph.nodes.tests import test_add
from node_graph.socket_spec import namespace as ns
from node_graph.engine.prefect import PrefectEngine
from typing import Any


def test_prefect_engine_resolves_states_and_graph_outputs():
    ng = NodeGraph(name="prefect-basic", outputs=ns(total=Any))
    add = ng.add_node(test_add, "add", x=40, y=2)

    ng.add_link(add.outputs.result, ng.outputs.total)

    engine = PrefectEngine(flow_name="prefect-basic-test")
    results = engine.run(ng)

    assert results["total"] == 42
    assert ng.outputs._value["total"] == 42

    prov = engine.recorder.to_json()
    process_nodes = prov["process_nodes"]
    graph_pid = next(
        pid for pid, info in process_nodes.items() if info["name"] == "prefect-basic"
    )
    assert process_nodes[graph_pid]["kind"] == "graph"
    edges = {(edge["src"], edge["dst"], edge["label"]) for edge in prov["edges"]}
    add_pid = next(pid for pid, info in process_nodes.items() if info["name"] == "add")
    assert (graph_pid, add_pid, "call") in edges


@node()
def double(x: float) -> float:
    return x * 2


@node.graph(outputs=ns(final=float))
def double_chain(x: float):
    first = double(x=x)
    second = double(x=first.result)
    return {"final": second.result}


def test_prefect_engine_nested_reuses_recorder():
    ng = NodeGraph(name="prefect-nested", outputs=ns(result=Any))
    chain_node = ng.add_node(double_chain, "chain", x=2)
    double_node = ng.add_node(double, "final", x=chain_node.outputs.final)
    ng.add_link(double_node.outputs.result, ng.outputs.result)

    engine = PrefectEngine(flow_name="prefect-nested")
    results = engine.run(ng)

    assert results["result"] == 16
    prov = engine.recorder.to_json()
    process_nodes = prov["process_nodes"]
    process_names = {proc["name"] for proc in process_nodes.values()}
    assert "chain" not in process_names
    assert {"chain__subgraph", "final"}.issubset(process_names)
    edges = {(edge["src"], edge["dst"], edge["label"]) for edge in prov["edges"]}
    graph_pid = next(
        pid for pid, info in process_nodes.items() if info["name"] == "prefect-nested"
    )
    assert process_nodes[graph_pid]["kind"] == "graph"
    nested_proc = next(
        pid for pid, info in process_nodes.items() if info["name"] == "chain__subgraph"
    )
    assert (graph_pid, nested_proc, "call") in edges
