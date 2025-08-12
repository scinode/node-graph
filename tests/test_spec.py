# tests/test_sockets_spec.py
from node_graph import NodeGraph, node, spec
from node_graph.socket import NodeSocketNamespace


def test_multiple_outputs():
    @node()
    def add_and_subtract(x: int, y: int) -> spec.namespace(sum=int, difference=int):
        return {"sum": x + y, "difference": x - y}

    ng = NodeGraph()
    n = ng.add_node(add_and_subtract, x=5, y=3)
    # static namespace is flattened to top-level outputs
    assert "sum" in n.outputs
    assert "difference" in n.outputs


def test_dynamic_output_named_inside_namespace():
    @node()
    def generate_squares(n: int) -> spec.namespace(squares=spec.dynamic(int)):
        return {"squares": {f"n_{i}": i * i for i in range(n)}}

    ng = NodeGraph()
    n = ng.add_node(generate_squares, n=5)
    # named dynamic namespace remains as a named field
    assert "squares" in n.outputs
    assert isinstance(n.outputs.squares, NodeSocketNamespace)


def test_top_level_dynamic_output_under_result():
    @node()
    def generate_squares(n: int) -> spec.dynamic(int):
        return {f"n_{i}": i * i for i in range(n)}

    ng = NodeGraph()
    n = ng.add_node(generate_squares, n=4)
    # unnamed dynamic is exposed under 'result'
    assert "result" in n.outputs
    assert isinstance(n.outputs.result, NodeSocketNamespace)


def test_dynamic_of_namespace_rows():
    Row = spec.namespace(val=int, squared=int)

    @node()
    def rows(n: int) -> spec.dynamic(Row):
        return {str(i): {"val": i, "squared": i * i} for i in range(n)}

    ng = NodeGraph()
    n = ng.add_node(rows, n=3)
    # dynamic where each entry is a small namespace
    assert "result" in n.outputs
    assert isinstance(n.outputs.result, NodeSocketNamespace)


def test_dynamic_with_fixed_fields_in_same_namespace():
    Out = spec.dynamic(int, total=int, meta=spec.namespace(alpha=float))

    @node()
    def both(n: int) -> Out:
        squares = {f"n_{i}": i * i for i in range(n)}
        return {"total": sum(squares.values()), "meta": {"alpha": 0.1}, **squares}

    ng = NodeGraph()
    n = ng.add_node(both, n=3)
    # dynamic entries + fixed siblings inside 'result'
    assert "result" in n.outputs
    assert isinstance(n.outputs.result, NodeSocketNamespace)
    assert "total" in n.outputs.result
    assert "meta" in n.outputs.result
