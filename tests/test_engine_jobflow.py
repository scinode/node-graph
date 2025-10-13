from node_graph import NodeGraph, node
from node_graph.nodes.tests import test_add
from node_graph.socket_spec import namespace as ns

from node_graph.engine.jobflow import JobflowEngine
from typing import Any


def test_jobflow_engine_executes_basic_graph():
    ng = NodeGraph(name="jobflow-basic", outputs=ns(total=Any))
    add1 = ng.add_node(test_add, "add1", x=1, y=2)
    add2 = ng.add_node(test_add, "add2", x=3, y=add1.outputs.result)
    ng.add_link(add2.outputs.result, ng.outputs.total)

    engine = JobflowEngine(name="jobflow-basic-test")
    results = engine.run(ng)

    assert results["total"] == 6


@node()
def double(x: float) -> float:
    return x * 2


@node.graph(outputs=ns(final=float))
def double_chain(x: float):
    first = double(x=x)
    second = double(x=first.result)
    return {"final": second.result}


def test_jobflow_engine_records_subgraph():
    ng = NodeGraph(name="jobflow-call-graph")
    chain_node = ng.add_node(double_chain, "chain", x=2)
    ng.add_node(double, "final", x=chain_node.outputs.final)

    engine = JobflowEngine(name="jobflow-call-engine")
    engine.run(ng)

    prov = engine.recorder.to_json()
    process_nodes = prov["process_nodes"].values()
    process_names = {proc["name"] for proc in process_nodes}
    assert "chain" not in process_names
    assert {"chain__subgraph", "final"}.issubset(process_names)
