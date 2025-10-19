# tests/test_sockets_spec.py
from node_graph import NodeGraph, node
from node_graph.socket import NodeSocketNamespace
from node_graph.socket_spec import namespace, dynamic


def test_nested_inputs():
    @node()
    def add_and_subtract(x: int, y: int, nested: namespace(a=int, b=int)):
        return {"sum": x + y, "difference": nested["a"] - nested["b"]}

    ng = NodeGraph()
    n = ng.add_node(add_and_subtract, x=5, y=3, nested={"a": 2, "b": 1})
    # static namespace is flattened to top-level outputs
    assert "x" in n.inputs
    assert "y" in n.inputs
    assert "a" in n.inputs.nested
    assert "b" in n.inputs.nested


def test_dynamic_inputs():
    @node()
    def generate_squares(n: int, dynamic_inputs: dynamic(int)):
        return {f"n_{i}": i * i for i in range(n)}

    ng = NodeGraph()
    n = ng.add_node(
        generate_squares, n=5, dynamic_inputs={f"input_{i}": i for i in range(5)}
    )
    # dynamic inputs are accessible as a dictionary
    assert "dynamic_inputs" in n.inputs
    assert n.inputs.dynamic_inputs._metadata.dynamic is True


def test_multiple_outputs():
    @node()
    def add_and_subtract(x: int, y: int) -> namespace(sum=int, difference=int):
        return {"sum": x + y, "difference": x - y}

    ng = NodeGraph()
    n = ng.add_node(add_and_subtract, x=5, y=3)
    # static namespace is flattened to top-level outputs
    assert "sum" in n.outputs
    assert "difference" in n.outputs


def test_dynamic_output_named_inside_namespace():
    @node()
    def generate_squares(n: int) -> namespace(squares=dynamic(int)):
        return {"squares": {f"n_{i}": i * i for i in range(n)}}

    ng = NodeGraph()
    n = ng.add_node(generate_squares, n=5)
    # named dynamic namespace remains as a named field
    assert "squares" in n.outputs
    assert isinstance(n.outputs.squares, NodeSocketNamespace)


def test_top_level_dynamic_output():
    @node()
    def generate_squares(n: int) -> dynamic(int):
        return {f"n_{i}": i * i for i in range(n)}

    ng = NodeGraph()
    n = ng.add_node(generate_squares, n=4)
    # unnamed dynamic is exposed under 'result'
    assert n.outputs._metadata.dynamic is True


def test_dynamic_of_namespace_rows():
    Row = namespace(val=int, squared=int)

    @node()
    def rows(n: int) -> dynamic(Row):
        return {str(i): {"val": i, "squared": i * i} for i in range(n)}

    ng = NodeGraph()
    n = ng.add_node(rows, n=3)
    # dynamic where each entry is a small namespace
    assert n.outputs._metadata.dynamic is True
    print(n.outputs._metadata)
    assert "val" in n.outputs._metadata.extras["item"]["fields"]


def test_dynamic_with_fixed_fields_in_same_namespace():
    Out = dynamic(int, total=int, meta=namespace(alpha=float))

    @node()
    def both(n: int) -> Out:
        squares = {f"n_{i}": i * i for i in range(n)}
        return {"total": sum(squares.values()), "meta": {"alpha": 0.1}, **squares}

    ng = NodeGraph()
    n = ng.add_node(both, n=3)
    # dynamic entries + fixed siblings
    assert "total" in n.outputs
    assert "meta" in n.outputs
    assert "alpha" in n.outputs.meta
    assert n.outputs._metadata.dynamic is True
