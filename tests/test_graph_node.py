from node_graph import NodeGraph, node
from node_graph.socket_spec import namespace, dynamic
from typing import Any


@node()
def add(x, y):
    return x + y


@node()
def multiply(x, y):
    return x * y


@node()
def two_outputs(x, y) -> namespace(x=Any, y=Any):
    return {"x": x, "y": y}


def test_build_graph(decorated_myadd_group):
    ng = decorated_myadd_group.build_graph(x=1, y=2)
    assert isinstance(ng, NodeGraph)
    assert len(ng.nodes) == 6
    assert len(ng.inputs) == 2
    assert len(ng.outputs) == 1
    assert len(ng.links) == 5


def test_run_as_a_node(decorated_myadd_group):
    ng = NodeGraph(name="test_outputs")
    addgroup1 = ng.add_node(decorated_myadd_group, "addgroup1", y=9)
    assert len(addgroup1.inputs) == 3  # 2 +  "_wait"
    assert len(addgroup1.outputs) == 3  # 1 + "_wait", "_outputs"


def test_namespace_outputs():
    @node.graph()
    def add_multiply(x, y) -> namespace(sum=Any, product=Any):
        return {"sum": add(x, y).result, "product": multiply(x, y).result}

    graph = add_multiply.build_graph(x=2, y=3)
    assert "sum" in graph.outputs
    assert "product" in graph.outputs

    @node.graph()
    def add_multiply(x, y) -> namespace(sum=Any, product=Any):
        return add(x, y).result, multiply(x, y).result

    graph = add_multiply.build_graph(x=2, y=3)
    assert "sum" in graph.outputs
    assert "product" in graph.outputs


def test_return_top_level_outputs():
    @node.graph()
    def test_graph(x, y) -> two_outputs.outputs:
        return two_outputs(x, y)

    graph = test_graph.build_graph(x=2, y=3)
    assert "x" in graph.outputs
    assert "y" in graph.outputs


def test_dynamic_outputs():
    @node.graph()
    def test_graph(x, y) -> dynamic(Any):
        return two_outputs(x, y)

    graph = test_graph.build_graph(x=2, y=3)
    assert "x" in graph.outputs
    assert "y" in graph.outputs

    @node.graph()
    def test_graph(x, y):
        return two_outputs(x, y)

    graph = test_graph.build_graph(x=2, y=3)
    assert "x" not in graph.outputs
