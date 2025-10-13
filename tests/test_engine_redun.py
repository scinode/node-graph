import pytest

redun = pytest.importorskip("redun")

from node_graph import NodeGraph, node
from node_graph.nodes.tests import test_add
from node_graph.socket_spec import namespace as ns

from node_graph.engine.redun import RedunEngine
from typing import Any

from redun.config import Config


def _temp_config(tmp_path):
    db_path = tmp_path / "redun-test.db"
    return Config(
        {
            "scheduler": {
                "backend": "sqlite",
                "db_uri": f"sqlite:///{db_path}",
            }
        }
    )


def test_redun_engine_executes_basic_graph(tmp_path):
    ng = NodeGraph(name="redun-basic", outputs=ns(total=Any))
    add1 = ng.add_node(test_add, "add1", x=1, y=2)
    add2 = ng.add_node(test_add, "add2", x=3, y=add1.outputs.result)
    ng.add_link(add2.outputs.result, ng.outputs.total)

    config = _temp_config(tmp_path)
    engine = RedunEngine(name="redun-basic-test", config=config)
    results = engine.run(ng)

    assert results["total"] == 6

    prov = engine.recorder.to_json()
    process_nodes = prov["process_nodes"]
    add2_pid = next(
        pid for pid, info in process_nodes.items() if info["name"] == "add2"
    )
    assert process_nodes[add2_pid]["state"] == "FINISHED"
    assert any(
        edge["dst"] == add2_pid and edge["label"] == "input:y" for edge in prov["edges"]
    )


@node()
def double(x: float) -> float:
    return x * 2


@node.graph(outputs=ns(final=float))
def double_chain(x: float):
    first = double(x=x)
    second = double(x=first.result)
    return {"final": second.result}


def test_redun_engine_records_call_edges(tmp_path):
    ng = NodeGraph(name="redun-call-graph", outputs=ns(result=Any))
    chain_node = ng.add_node(double_chain, "chain", x=2)
    double_node = ng.add_node(double, "final", x=chain_node.outputs.final)
    ng.outputs.result = double_node.outputs.result

    config = _temp_config(tmp_path)
    engine = RedunEngine(name="redun-call-engine", config=config)
    engine.run(ng)

    prov = engine.recorder.to_json()
    process_nodes = prov["process_nodes"].values()
    process_names = {proc["name"] for proc in process_nodes}
    assert "chain" not in process_names
    assert {"chain__subgraph", "final"}.issubset(process_names)
    assert any(
        name.startswith("double")
        for name in process_names
        if name not in {"redun-call-graph", "chain__subgraph", "final"}
    )
