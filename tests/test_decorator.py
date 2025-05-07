from node_graph.decorator import build_node_from_callable
from node_graph.decorator import node
from node_graph.manager import get_current_graph, set_current_graph
from node_graph import NodeGraph, NodePool
from node_graph.nodes.factory.base import BaseNodeFactory


def test_build_node():
    """Build node from a callable."""
    ndata = {
        "executor": "math.sqrt",
    }
    NodeCls = build_node_from_callable(**ndata)
    ng = NodeGraph(name="test_create_node")
    task1 = ng.add_node(NodeCls, "add1")
    assert task1.to_dict()["executor"]["mode"] == "module"
    assert len(ng.nodes) == 1
    "x" in ng.nodes[0].get_input_names()


def test_get_current_graph():

    g = get_current_graph()
    assert isinstance(g, NodeGraph)


def test_set_current_graph(decorated_myadd):
    sum = decorated_myadd(1, 2)
    g = get_current_graph()
    assert g == sum._node.graph
    g2 = NodeGraph()
    set_current_graph(g2)
    assert get_current_graph() == g2


def test_create_node():
    """Build node on-the-fly."""
    ndata = {
        "identifier": "add",
        "properties": [{"identifier": "node_graph.float", "name": "x", "default": 3}],
        "inputs": {
            "name": "inputs",
            "identifier": "node_graph.namespace",
            "sockets": {
                "y": {
                    "identifier": "node_graph.float",
                    "name": "y",
                    "property": {"identifier": "node_graph.float", "default": 10},
                }
            },
        },
        "outputs": {
            "name": "outputs",
            "identifier": "node_graph.namespace",
            "sockets": {
                "result": {"identifier": "node_graph.any", "name": "result"},
            },
        },
        "executor": {"module_path": "numpy.add"},
    }
    NodeCls = BaseNodeFactory(ndata)
    ng = NodeGraph(name="test_create_node")
    ng.add_node(NodeCls, "add1")
    assert len(ng.nodes) == 1
    assert ng.nodes[0].properties[0].default == 3
    assert ng.nodes[0].inputs[0].property.default == 10


def test_decorator_args() -> None:
    """Test passing parameters to decorators."""
    from node_graph.socket import NodeSocketNamespace

    @node()
    def test(a, /, b, *, c, d=1, **e):
        return 1

    task1 = test._NodeCls()
    assert task1.get_executor()["mode"] == "pickled_callable"
    assert task1.inputs["e"]._link_limit > 1
    assert task1.inputs["e"]._identifier == "node_graph.namespace"
    assert task1.inputs["c"]._metadata.required is True
    assert task1.inputs["d"]._metadata.required is False
    assert task1.inputs["d"]._metadata.function_socket is True
    assert task1.inputs["d"].property.default == 1
    assert set(task1.args_data["args"]) == set(["a"])
    assert set(task1.args_data["kwargs"]) == set(["b", "c", "d"])
    assert task1.args_data["var_kwargs"] == "e"
    assert isinstance(task1.inputs.e, NodeSocketNamespace)
    assert task1.inputs.e._metadata.dynamic is True


def test_decorator_parameters() -> None:
    """Test passing parameters to decorators."""

    @node(
        inputs=[{"name": "c"}, {"name": "kwargs"}],
        properties=[{"name": "d", "default": 3}],
        outputs=[{"name": "sum"}, {"name": "product"}],
    )
    def test(*x, a, b=1, **kwargs):
        return {"sum": a + b, "product": a * b}

    test1 = test._NodeCls()
    assert test1.inputs["kwargs"]._link_limit == 1e6
    assert test1.inputs["kwargs"]._identifier == "node_graph.namespace"
    # user defined the c input manually
    assert "c" in test1.get_input_names()
    assert "d" in test1.get_property_names()
    assert set(test1.args_data["args"]) == set([])
    assert set(test1.args_data["kwargs"]) == set(["a", "b", "c", "d"])
    assert test1.args_data["var_args"] == "x"
    assert "sum" in test1.get_output_names()
    assert "product" in test1.get_output_names()
    # create another node
    test2 = test._NodeCls()
    assert test2.inputs.b.value == test1.inputs.b.value


def test_socket():
    @node(outputs=[{"name": "sum"}, {"name": "product"}])
    def func(x: int, y: int = 1):
        return {"sum": x + y, "product": x * y}

    outputs = func(1, 2)
    assert "sum" in outputs
    assert "product" in outputs
    assert outputs._node.inputs.x._identifier == "node_graph.int"
    assert outputs._node.inputs.y.property.default == 1


def create_test_node_group():
    ng = NodeGraph()
    add1 = ng.add_node(NodePool.node_graph.test_add, "add1")
    add2 = ng.add_node(NodePool.node_graph.test_add, "add2")
    add3 = ng.add_node(NodePool.node_graph.test_add, "add3")
    ng.add_link(add1.outputs[0], add3.inputs[0])
    ng.add_link(add2.outputs[0], add3.inputs[1])
    ng.inputs.x = add1.inputs.x
    ng.inputs.y = add2.inputs.x
    ng.outputs.result = add3.outputs.result
    return ng


def test_decorator_node(ng_decorator):

    ng = ng_decorator
    ng.name = "test_decorator_node"
    assert len(ng.nodes) == 4
    assert len(ng.links) == 3


def test_decorator_node_group(decorated_myadd, decorated_myadd_group):
    ng = NodeGraph(name="test_decorator_node_group")
    addgroup1 = ng.add_node(decorated_myadd_group, "addgroup1", y=9)
    add1 = ng.add_node(decorated_myadd, "add1", x=8)
    ng.add_link(add1.outputs["result"], addgroup1.inputs[0])
    assert len(ng.nodes) == 2


def test_decorator_node_in_decorator_node(decorated_myadd, node_with_decorated_node):

    ng = NodeGraph(name="test_decorator_node_in_decorator_node")
    add1 = ng.add_node(decorated_myadd, "add1", x=8)
    add2 = ng.add_node(node_with_decorated_node, y=9)
    ng.add_link(add1.outputs["result"], add2.inputs[0])
    assert len(ng.nodes) == 2
