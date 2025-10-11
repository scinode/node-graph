from node_graph import NodeGraph, node, dynamic
from node_graph.nodes.tests import test_add
from node_graph.socket_spec import namespace as ns

from node_graph.engine.direct import DirectEngine
from node_graph.engine.provenance import ProvenanceRecorder, content_hash
from typing import Annotated


@node()
def double(x: float) -> float:
    return x * 2


@node.graph(outputs=ns(final=float))
def double_chain(x: float):
    first = double(x=x)
    second = double(x=first.result)
    return {"final": second.result}


def test_direct_engine_executes_basic_graph():
    ng = NodeGraph(name="direct-basic")
    add1 = ng.add_node(test_add, "add1", x=1, y=2)
    ng.add_node(test_add, "add2", x=3, y=add1.outputs.result)

    engine = DirectEngine()
    results = engine.run(ng)

    assert results["add1"]["result"] == 3
    assert results["add2"]["result"] == 6

    proc_data = engine.recorder.to_json()
    assert "proc:add1:1" in proc_data["process_nodes"]
    assert proc_data["process_nodes"]["proc:add2:1"]["state"] == "FINISHED"

    hash_three = content_hash(3)
    expected_edge = {
        "src": f"data:{hash_three}",
        "dst": "proc:add2:1",
        "label": "input:y",
    }
    assert expected_edge in proc_data["edges"]


def test_direct_engine_records_subgraph_provenance():
    ng = NodeGraph(name="direct-subgraph")
    graph_node = ng.add_node(double_chain, "chain", x=2)
    ng.add_node(double, "final", x=graph_node.outputs.final)

    recorder = ProvenanceRecorder("direct-subgraph-test")
    engine = DirectEngine(name="direct-subgraph", recorder=recorder)
    results = engine.run(ng)

    assert results["chain"]["final"] == 8
    assert results["final"]["result"] == 16

    process_names = {
        proc["name"] for proc in recorder.to_json()["process_nodes"].values()
    }
    assert {"chain", "final"}.issubset(process_names)
    assert any(
        name.startswith("double")
        for name in process_names
        if name not in {"chain", "final"}
    )


def test_direct_engine_handles_nested_and_dynamic_outputs():
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
    engine = DirectEngine()
    values = engine.run(ng)

    assert values["add_multiply"]["sum"] == 5
    assert values["generate_square_numbers"]["square_4"] == 16
    assert values["add_multiply1"]["product"] == 30
    assert len(values["generate_square_numbers"]) == 5

    prov = engine.recorder.to_json()

    nested_labels = {
        edge["label"] for edge in prov["edges"] if edge["dst"] == "proc:add_multiply1:1"
    }
    assert {"input:data.x", "input:data.y"}.issubset(nested_labels)

    dynamic_labels = {
        edge["label"]
        for edge in prov["edges"]
        if edge["src"] == "proc:generate_square_numbers:1"
    }
    assert dynamic_labels == {f"output:square_{i}" for i in range(5)}
