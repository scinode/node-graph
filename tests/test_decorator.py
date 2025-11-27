from node_graph.decorator import build_task_from_callable
from node_graph.manager import get_current_graph, set_current_graph
from node_graph import Graph, task
from node_graph.socket_spec import namespace
from node_graph.task_spec import SchemaSource
import pytest
from node_graph.tasks.tests import test_add


def test_build_task():
    """Build task from a callable."""
    from math import sqrt

    TaskCls = build_task_from_callable(sqrt)
    ng = Graph(name="test_create_task")
    task1 = ng.add_task(TaskCls, "add1")
    ndata = task1.to_dict()
    assert ndata["spec"]["schema_source"] == SchemaSource.EMBEDDED
    assert "inputs" in task1.to_dict()["spec"]
    assert len(ng.tasks) == 4
    "x" in ng.tasks[-1].inputs


def test_importable_task():
    object.__setattr__(test_add._spec, "schema_source", SchemaSource.EMBEDDED)
    ng = Graph(name="test_create_task")
    task1 = ng.add_task(test_add, "add1")
    assert task1.spec.schema_source == SchemaSource.EMBEDDED
    # when store in db, we will check if the callable is a handle
    # if yes, will override the schema source to HANDLE
    ndata = task1.to_dict()
    assert ndata["spec"]["schema_source"] == SchemaSource.HANDLE
    assert "inputs" not in task1.to_dict()["spec"]


def test_get_current_graph():

    g = get_current_graph()
    assert isinstance(g, Graph)


def test_set_current_graph(decorated_myadd):
    sum = decorated_myadd(1, 2)
    g = get_current_graph()
    assert g == sum._task.graph
    g2 = Graph()
    set_current_graph(g2)
    assert get_current_graph() == g2


def test_decorator_args() -> None:
    """Test passing parameters to decorators."""
    from node_graph.socket import TaskSocketNamespace

    @task()
    def test(a, /, b, *, c, d=1, **e):
        return 1

    task1 = test()._task
    assert task1.get_executor().mode == "pickled_callable"
    assert task1.inputs.e._link_limit > 1
    assert task1.inputs.e._identifier == "node_graph.namespace"
    assert task1.inputs.c._metadata.required is True
    assert task1.inputs.d._metadata.required is False
    assert task1.inputs.d._metadata.extras.get("function_socket") is True
    assert task1.inputs.d.property.default == 1
    assert set(task1.args_data["args"]) == set(["a"])
    assert set(task1.args_data["kwargs"]) == set(["b", "c", "d"])
    assert task1.args_data["var_kwargs"] == "e"
    assert isinstance(task1.inputs.e, TaskSocketNamespace)
    assert task1.inputs.e._metadata.dynamic is True


def test_decorator_var_positional() -> None:
    """Test passing parameters to decorators."""

    @task()
    def test(*x):
        pass

    with pytest.raises(ValueError, match="VAR_POSITIONAL is not supported."):
        test()._task


def test_decorator_parameters() -> None:
    """Test passing parameters to decorators."""

    @task(
        outputs=namespace(sum=any, product=any),
    )
    def test(a, c: namespace(c1=any, c2=any), b=1, **kwargs):
        return {"sum": a + b, "product": a * b}

    test1 = test()._task
    assert test1.inputs["kwargs"]._link_limit == 1000000
    assert test1.inputs["kwargs"]._identifier == "node_graph.namespace"
    # user defined the c input manually
    assert "c" in test1.inputs
    assert "c1" in test1.inputs.c
    assert set(test1.args_data["args"]) == set([])
    assert set(test1.args_data["kwargs"]) == set(["a", "b", "c"])
    assert "sum" in test1.get_output_names()
    assert "product" in test1.get_output_names()
    # create another task
    test2 = test()._task
    assert test2.inputs.b.value == test1.inputs.b.value


def test_socket():
    @task(outputs=namespace(sum=any, product=any))
    def func(x: int, y: int = 1):
        return {"sum": x + y, "product": x * y}

    outputs = func(1, 2)
    assert "sum" in outputs
    assert "product" in outputs
    assert outputs._task.inputs.x._identifier == "node_graph.int"
    assert outputs._task.inputs.y.property.default == 1
    # test socket order
    assert outputs[0]._name == "sum"


def create_test_task_group():
    ng = Graph()
    add1 = ng.add_task(test_add, "add1")
    add2 = ng.add_task(test_add, "add2")
    add3 = ng.add_task(test_add, "add3")
    ng.add_link(add1.outputs[0], add3.inputs[0])
    ng.add_link(add2.outputs[0], add3.inputs[1])
    ng.inputs.x = add1.inputs.x
    ng.inputs.y = add2.inputs.x
    ng.outputs.result = add3.outputs.result
    return ng


def test_decorator_task(ng_decorator):

    ng = ng_decorator
    ng.name = "test_decorator_task"
    assert len(ng.tasks) == 7
    assert len(ng.links) == 3


def test_decorator_task_group(decorated_myadd, decorated_myadd_group):
    ng = Graph(name="test_decorator_task_group")
    addgroup1 = ng.add_task(decorated_myadd_group, "addgroup1", y=9)
    add1 = ng.add_task(decorated_myadd, "add1", x=8)
    ng.add_link(add1.outputs["result"], addgroup1.inputs[0])
    assert len(ng.tasks) == 5


def test_decorator_task_in_decorator_task(decorated_myadd, task_with_decorated_task):

    ng = Graph(name="test_decorator_task_in_decorator_task")
    add1 = ng.add_task(decorated_myadd, "add1", x=8)
    add2 = ng.add_task(task_with_decorated_task, y=9)
    ng.add_link(add1.outputs["result"], add2.inputs[0])
    assert len(ng.tasks) == 5


def test_use_socket_view():
    @task(outputs=namespace(sum=any, product=any))
    def test(a, b):
        return {"sum": a + b, "product": a * b}

    @task.graph(outputs=test.outputs)
    def test_graph(a, b):
        return test(a, b)

    graph = test_graph.build(a=1, b=2)
    assert "sum" in graph.outputs
    assert "product" in graph.outputs
