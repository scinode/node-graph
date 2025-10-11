from node_graph import NodeGraph, node
from node_graph.nodes.tests import test_add
from node_graph.socket_spec import namespace as ns

from node_graph.engine.direct import DirectEngine
from node_graph.engine.provenance import ProvenanceRecorder, content_hash


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
