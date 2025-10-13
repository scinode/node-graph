import shutil
from typing import Any

import pytest

pyiron_base = pytest.importorskip("pyiron_base")

from node_graph import NodeGraph, node
from node_graph.nodes.tests import test_add
from node_graph.socket_spec import namespace as ns
from node_graph.engine.pyiron import PyironEngine


def make_engine(tmp_path, name="pyiron-test"):
    project_path = tmp_path / f"proj-{name}"
    engine = PyironEngine(
        name=name,
        project_path=str(project_path),
        cleanup_project=False,
        auto_cleanup_jobs=True,
    )
    return engine, project_path


def test_pyiron_engine_executes_basic_graph(tmp_path):
    ng = NodeGraph(name="pyiron-basic", outputs=ns(total=Any))
    add1 = ng.add_node(test_add, "add1", x=1, y=2)
    add2 = ng.add_node(test_add, "add2", x=3, y=add1.outputs.result)
    ng.add_link(add2.outputs.result, ng.outputs.total)

    engine, project_path = make_engine(tmp_path, name="pyiron-basic")
    try:
        results = engine.run(ng)
        assert results["total"] == 6
    finally:
        shutil.rmtree(project_path, ignore_errors=True)


@node()
def double(x: float) -> float:
    return x * 2


@node.graph(outputs=ns(final=float))
def double_chain(x: float):
    first = double(x=x)
    second = double(x=first.result)
    return {"final": second.result}


def test_pyiron_engine_records_subgraph(tmp_path):
    ng = NodeGraph(name="pyiron-call-graph")
    chain_node = ng.add_node(double_chain, "chain", x=2)
    ng.add_node(double, "final", x=chain_node.outputs.final)

    engine, project_path = make_engine(tmp_path, name="pyiron-graph")
    try:
        engine.run(ng)
        prov = engine.recorder.to_json()
        process_names = {proc["name"] for proc in prov["process_nodes"].values()}
        assert "chain" not in process_names
        assert {"chain__subgraph", "final"}.issubset(process_names)
    finally:
        shutil.rmtree(project_path, ignore_errors=True)
