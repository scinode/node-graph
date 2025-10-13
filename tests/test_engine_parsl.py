import pytest

parsl = pytest.importorskip("parsl")

from node_graph import NodeGraph, node, dynamic
from node_graph.nodes.tests import test_add
from node_graph.socket_spec import namespace as ns

from node_graph.engine.parsl import ParslEngine
from node_graph.engine.provenance import ProvenanceRecorder
from typing import Annotated, Any


@pytest.fixture(autouse=True)
def _clear_parsl():
    try:
        parsl.clear()
    except Exception:
        pass
    yield
    try:
        parsl.clear()
    except Exception:
        pass


@node()
def double(x: float) -> float:
    return x * 2


@node.graph(outputs=ns(final=float))
def double_chain(x: float):
    first = double(x=x)
    second = double(x=first.result)
    return {"final": second.result}


def test_parsl_engine_executes_basic_graph():
    ng = NodeGraph(name="parsl-basic", outputs=ns(total=Any))
    add1 = ng.add_node(test_add, "add1", x=1, y=2)
    add2 = ng.add_node(test_add, "add2", x=3, y=add1.outputs.result)
    ng.add_link(add2.outputs.result, ng.outputs.total)

    engine = ParslEngine(name="parsl-basic-test")
    results = engine.run(ng)

    assert results["total"] == 6

    prov = engine.recorder.to_json()
    add2_pid = next(
        pid for pid, info in prov["process_nodes"].items() if info["name"] == "add2"
    )
    assert prov["process_nodes"][add2_pid]["state"] == "FINISHED"
    assert any(
        edge["dst"] == add2_pid and edge["label"] == "input:y" for edge in prov["edges"]
    )


def test_parsl_engine_records_subgraph_provenance():
    ng = NodeGraph(name="parsl-subgraph", outputs=ns(result=Any))
    graph_node = ng.add_node(double_chain, "chain", x=2)
    final_node = ng.add_node(double, "final", x=graph_node.outputs.final)
    ng.add_link(final_node.outputs.result, ng.outputs.result)

    recorder = ProvenanceRecorder("parsl-subgraph-test")
    engine = ParslEngine(name="parsl-subgraph", recorder=recorder)
    results = engine.run(ng)

    assert results["result"] == 16

    process_nodes = recorder.to_json()["process_nodes"].values()
    process_names = {proc["name"] for proc in process_nodes}
    assert "chain" not in process_names
    assert {"chain__subgraph", "final"}.issubset(process_names)
    assert any(
        name.startswith("double")
        for name in process_names
        if name not in {"parsl-subgraph", "final", "chain__subgraph"}
    )


def test_parsl_engine_handles_nested_and_dynamic_outputs():
    @node()
    def generate_square_numbers(
        n: int,
    ) -> Annotated[dict, dynamic(int)]:
        return {f"square_{i}": i**2 for i in range(n)}

    @node()
    def add_multiply(
        data: Annotated[dict, ns(x=int, y=int)],
    ) -> Annotated[dict, ns(sum=int, product=int)]:
        return {"sum": data["x"] + data["y"], "product": data["x"] * data["y"]}

    @node.graph(
        outputs=ns(
            square=generate_square_numbers.outputs,
            add_multiply=add_multiply.outputs,
        )
    )
    def composed(
        data: Annotated[dict, add_multiply.inputs.data],
    ):
        out1 = add_multiply(data=data)
        square_numbers = generate_square_numbers(out1["sum"])
        out2 = add_multiply(data={"x": out1["sum"], "y": out1["product"]})
        return {"square": square_numbers, "add_multiply": out2}

    ng = composed.build(data={"x": 2, "y": 3})
    engine = ParslEngine(name="parsl-dynamic")
    values = engine.run(ng)

    assert values["add_multiply"]["sum"] == 11
    assert values["square"]["square_4"] == 16
    assert values["add_multiply"]["product"] == 30
    assert len(values["square"]) == 5


def test_parsl_engine_records_call_edges():
    ng = NodeGraph(name="parsl-call-graph")
    chain_node = ng.add_node(double_chain, "chain", x=2)
    ng.add_node(double, "final", x=chain_node.outputs.final)

    engine = ParslEngine(name="parsl-call-engine")
    engine.run(ng)

    prov = engine.recorder.to_json()
    process_nodes = prov["process_nodes"]

    graph_proc = next(
        pid for pid, info in process_nodes.items() if info["name"] == "parsl-call-graph"
    )
    assert process_nodes[graph_proc]["kind"] == "graph"

    nested_proc = next(
        pid for pid, info in process_nodes.items() if info["name"] == "chain__subgraph"
    )
    edges = {(edge["src"], edge["dst"], edge["label"]) for edge in prov["edges"]}
    assert (graph_proc, nested_proc, "call") in edges
