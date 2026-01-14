from node_graph import Graph, task, namespace
import pytest
from typing import Any
from node_graph.tasks.tests import test_float, test_add


@pytest.fixture
def test_ng():
    """A test node_graph."""

    @task(
        inputs=namespace(
            input1=namespace(x=Any, y=Any), input2=namespace(x=Any, y=Any)
        ),
        outputs=namespace(
            output1=namespace(x=Any, y=Any), output2=namespace(x=Any, y=Any)
        ),
    )
    def add():
        pass

    ng = Graph(name="test_graph")
    ng.add_task(add, "add1")
    ng.add_task(add, "add2")
    ng.add_task(add, "add3")
    return ng


def test_from_dict(ng_decorator):
    """Export Graph to dict."""
    ng = ng_decorator
    ntdata = ng_decorator.to_dict()
    ng1 = Graph.from_dict(ntdata)
    assert len(ng.tasks) == len(ng1.tasks)
    assert len(ng.links) == len(ng1.links)
    assert ng.to_dict() == ng1.to_dict()


def test_new_node(ng):
    """Test new task."""
    ng = Graph(name="test_graph")
    n1 = ng.add_task(test_add)
    n2 = ng.add_task(test_add)
    assert n1.name == "test_add"
    assert n2.name == "test_add1"
    assert len(ng.tasks) == 5
    # add builtin task is not allowed
    name = "graph_inputs"
    with pytest.raises(
        ValueError,
        match=f"Name {name} can not be used, it is reserved.",
    ):
        ng.add_task(test_add, name=name)


def test_set_inputs(decorated_myadd):
    ng = Graph(
        name="test_graph",
        inputs=namespace(x=Any, y=Any),
        outputs=namespace(result=Any),
    )
    n1 = ng.add_task(decorated_myadd, x=ng.inputs.x, name="add1")
    n2 = ng.add_task(decorated_myadd, x=ng.inputs.y, y=n1.outputs.result, name="add2")
    ng.outputs.result = n2.outputs.result
    ng.set_inputs({"graph_inputs": {"x": 1, "y": 2}, "add1": {"y": 2}})
    assert ng.inputs.x.value == 1
    assert ng.inputs.y.value == 2
    assert ng.tasks["add1"].inputs.y.value == 2


def test_delete_node(ng):
    """Test delete task."""
    n = len(ng.tasks)
    nlink = len(ng.links)
    ng.add_task(test_add, name="add3")
    ng.add_link(ng.tasks["add1"].outputs[0], ng.tasks["add3"].inputs["y"])
    assert len(ng.tasks) == n + 1
    assert len(ng.links) == nlink + 1
    ng.delete_tasks(["add3"])
    assert len(ng.tasks) == n
    assert len(ng.links) == nlink


def test_copy(ng):
    """Test copy task graph"""
    n = len(ng.tasks)
    nlink = len(ng.links)
    ng1 = ng.copy()
    assert len(ng1.tasks) == n
    assert len(ng1.links) == nlink


def test_add_another_graph(ng):
    """Test add another graph."""
    n = len(ng.tasks)
    nlink = len(ng.links)
    ng1 = Graph(name="test_add")
    ng1.add_task(test_float, "float3", value=4.0, t=3)
    ng1.add_task(test_float, "float4", value=3.0)
    ng = ng + ng1
    assert len(ng.tasks) == n + 2
    assert len(ng.links) == nlink


def test_copy_subset(ng):
    """Test copy subset of tasks."""
    ng1 = ng.copy_subset(["add1", "add2"])
    assert len(ng1.tasks) == 6
    assert len(ng1.links) == 2
    assert "float1" in ng1.get_task_names()


def test_get_items(ng):
    """Test get items."""
    ng1 = ng[["add1", "add2"]]
    assert len(ng1.tasks) == 6
    assert len(ng1.links) == 2
    assert "float1" in ng1.get_task_names()


def test_load_graph():
    @task(
        outputs=namespace(sum=any, product=any, nested=namespace(sum=any, product=any)),
    )
    def test(a, b=1, nested: namespace(d=any, f=namespace(g=any, h=any)) = {}):
        return {
            "sum": a + b,
            "product": a * b,
            "nested": {"sum": a + b, "product": a * b},
        }

    ng = Graph()
    test1 = ng.add_task(test, "test1")
    test1.set_inputs(
        {
            "a": 1,
            "b": 2,
            "nested": {"d": 2, "f": {"g": 1, "h": 2}},
        }
    )
    ngdata = ng.to_dict()
    # load graph
    ng1 = Graph.from_dict(ngdata)
    assert "sum" in ng1.tasks.test1.outputs.nested
    assert ng1.tasks.test1.inputs._value == ng.tasks.test1.inputs._value


def test_expose_inputs(test_ng):
    """Test generation of inputs from tasks"""
    ng = test_ng
    ng.expose_inputs()
    assert "add1" in ng.inputs
    assert "add1" in ng.spec.inputs.fields
    assert ng.inputs.add1._value == ng.tasks["add1"].inputs._value
    assert ng.inputs.add2._value == ng.tasks["add2"].inputs._value


def test_expose_inputs_names(test_ng):
    """Test generation of inputs from named tasks"""
    ng = test_ng
    ng.expose_inputs(names=["add1", "add2"])
    assert "add1" in ng.inputs
    assert "add2" in ng.inputs
    assert "add3" not in ng.inputs
    assert ng.inputs.add2._value == ng.tasks["add2"].inputs._value


def test_expose_inputs_names_invalid(test_ng):
    """Test that input generation fails for invalid name"""
    name = "missing"
    with pytest.raises(
        ValueError,
        match="The following tasks do not exist:",
    ):
        test_ng.expose_inputs(names=[name])


def test_expose_inputs_skip_linked(test_ng):
    """Test generation of inputs from tasks, skip linked sockets"""
    ng = test_ng
    ng.add_link(ng.tasks.add1.outputs.output1.x, ng.tasks.add2.inputs.input1.x)
    ng.expose_inputs()
    assert "add2" in ng.inputs
    assert "input1.x" not in ng.inputs.add2
    assert "input1.y" in ng.inputs.add2
    # outputs will still have all sockets
    ng.expose_outputs()
    assert "add1" in ng.outputs
    assert "output1.x" in ng.outputs.add1
    assert "output1.y" in ng.outputs.add1


def test_expose_outputs(test_ng):
    """Test generation of outputs from tasks"""
    ng = test_ng
    ng.expose_outputs()
    assert "add1" in ng.outputs
    assert "add1" in ng.spec.outputs.fields
    assert ng.outputs.add1._value == ng.tasks["add1"].outputs._value
    assert ng.outputs.add2._value == ng.tasks["add2"].outputs._value


def test_graph_metadata_roundtrip():
    meta = {"foo": "bar", "definition": {"package_version": "1.2.3"}}
    ng = Graph(name="meta_graph", metadata=meta)
    payload = ng.to_dict()
    restored = Graph.from_dict(payload)
    assert restored._metadata["foo"] == "bar"
    assert restored.get_metadata()["foo"] == "bar"
    assert restored._metadata["definition"]["package_version"] == "1.2.3"


def test_graph_definition_metadata_from_build():
    @task.graph(outputs=namespace(result=Any))
    def test_graph(x):
        return {"result": x}

    ng = test_graph.build(1)
    assert "definition" in ng._metadata
    assert ng._metadata["definition"].get("task_identifier") == "test_graph.test_graph"


def test_expose_outputs_names(test_ng):
    """Test generation of outputs from named tasks"""
    ng = test_ng
    ng.expose_outputs(names=["add1"])
    assert ng.outputs.add1._value == ng.tasks["add1"].outputs._value
    assert "add2" not in ng.outputs


def test_expose_outputs_names_invalid(test_ng):
    """Test that output generation fails for invalid name"""
    name = "missing"
    with pytest.raises(
        ValueError,
        match="The following tasks do not exist:",
    ):
        test_ng.expose_outputs(names=[name])


def test_build_inputs_outputs(ng):
    """Test build graph inputs and outputs."""
    ng = Graph(
        name="test_graph_inputs_outputs",
        inputs=namespace(a=any, b=any, c=namespace(x=any, y=any)),
        outputs=namespace(sum=any, product=any, nested=namespace(sum=any, product=any)),
    )
    assert "a" in ng.inputs
    assert "x" in ng.inputs.c
    assert "sum" in ng.outputs
    assert "sum" in ng.outputs.nested
    assert ng.inputs._metadata.child_default_link_limit == 1000000
