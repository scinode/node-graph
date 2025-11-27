from node_graph import Graph
from node_graph.tasks.tests import test_add
from node_graph.task import Task
from node_graph.socket_spec import namespace
import pytest


def test_base_task():
    """Create a task.
    Append it to a graph.
    """
    ng = Graph(name="test_base_task")
    n = Task()
    # added to graph
    ng.append_task(n)
    assert n.graph == ng
    # copy
    n1 = n.copy(name="n1")
    assert n1.graph == ng
    assert n1.name == "n1"


def test_builtin_sockets():
    task = Task()
    assert "_wait" in task.inputs
    assert "_outputs" in task.outputs
    assert task.inputs._wait._metadata.required is False


def test_id_name():

    ng = Graph(name="test_id_name")
    # auto generate name for the task
    math1 = ng.add_task(test_add)
    assert math1.name == "test_add"
    math2 = ng.add_task(test_add)
    assert math2.name == "test_add1"
    # set task name manually
    math3 = ng.add_task(test_add, name="Math3")
    assert math3.name == "Math3"


def test_set_task_input():
    ng = Graph(name="test_set_inputs")
    add1 = ng.add_task(test_add, "add1")
    add2 = ng.add_task(test_add, "add2")
    add2.set_inputs({"x": add1})
    assert len(ng.links) == 1
    assert add2.inputs["x"].property.value is None


def test_set_link_as_input():
    ng = Graph(name="test_set_inputs")
    add1 = ng.add_task(test_add, "add1")
    add2 = ng.add_task(test_add, "add2")
    add2.set_inputs({"x": add1.outputs["result"]})
    assert len(ng.links) == 1
    assert add2.inputs["x"].property.value is None


def test_set_non_exit_input_for_dynamic_input():
    task = Task()
    task.inputs._metadata.dynamic = True
    task.set_inputs({"x": 1})
    assert task.inputs.x.value == 1


def test_set_property():

    ng = Graph(name="test_set_property")
    math = ng.add_task(test_add, "Math")
    math.inputs["x"].property.value = 2
    assert math.inputs["x"].property.value == 2


def test_to_dict():

    ng = Graph(name="test_to_dict")
    math = ng.add_task(test_add, "Math")
    math.inputs["x"].property.value = 2
    data = math.to_dict()
    assert "spec" in data
    assert data["spec"]["identifier"] == "test_add"


def test_copy():
    """Copy task.

    All the properties and sockets should be copied.

    """

    ng = Graph(name="test_copy")
    math = ng.add_task(test_add, "Math", t=5, x=2)
    assert len(ng.tasks) == 4
    math1 = math.copy()
    assert math1.inputs["t"].value == 5
    assert math1.inputs["x"].property.value == 2
    assert math1.graph.uuid == ng.uuid
    assert math1.name == f"{math.name}_copy"
    #
    ng.append_task(math1)
    assert len(ng.tasks) == 5


def test_check_name():
    """Check name when creating a task."""
    ng = Graph(name="test_check_name")
    ng.add_task(test_add, "add1")
    # check if it raises an error if the name is already taken
    try:
        ng.add_task(test_add, "add1")
    except ValueError as e:
        assert str(e) == "add1 already exists, please choose another name."
    else:
        raise AssertionError("Name already exists.")

    try:
        ng.add_task("node_graph.test_ad", "add2")
    except ValueError as e:
        assert (
            "Identifier: node_graph.test_ad is not defined. Did you mean node_graph"
            in str(e)
        )
    else:
        raise AssertionError("Name already exists.")
    key = "x 1"
    with pytest.raises(
        ValueError,
        match="spaces are not allowed",
    ):
        ng.add_task(test_add, key)


def test_repr():
    """Test __repr__ method."""
    ng = Graph(name="test_repr")
    ng.add_task(test_add, "add1")
    assert (
        repr(ng.tasks)
        == 'TaskCollection(parent = "test_repr", tasks = ["graph_inputs", "graph_outputs", "graph_ctx", "add1"])'
    )


def test_graph_task():
    ng = Graph(name="test_graph_task")
    sub_ng = Graph(
        name="sub_graph",
        inputs=namespace(x=int, y=int),
        outputs=namespace(result=int),
    )
    sub_ng.add_task(test_add, "add1")
    sub_ng.add_task(test_add, "add2", x=sub_ng.tasks.add1.outputs.result)
    ng.add_task(sub_ng, "sub_ng")
    assert len(ng.tasks) == 4
    assert len(ng.tasks.sub_ng.tasks) == 5
    assert len(ng.tasks.sub_ng.links) == 1
    assert "add1" in ng.tasks.sub_ng.tasks
    # check inputs
    assert "x" in ng.tasks.sub_ng.inputs
    assert "result" in ng.tasks.sub_ng.outputs
    assert set(ng.tasks.sub_ng.inputs._get_all_keys()) == {
        "x",
        "y",
        "_wait",
    }
    assert set(ng.tasks.sub_ng.outputs._get_all_keys()) == {
        "result",
        "_outputs",
        "_wait",
    }


def test_execute(decorated_myadd):
    result = decorated_myadd(1, 2)
    result = result._task.execute()


def test_add_inputs():
    task = Task()
    task.add_input("node_graph.int", "e")
    assert "e" in task.inputs


def test_add_error_handler():
    def sample_handler(task):
        """dummy handler"""

    task = Task()
    task.add_error_handler(
        {"test": {"executor": sample_handler, "exit_codes": [1, 2], "max_retries": 3}}
    )
    assert len(task.error_handlers) == 1


def test_add_input_outputs_spec():
    task = Task()
    task.add_input_spec("node_graph.int", "a")
    task.add_input_spec("node_graph.int", "b")
    task.add_output_spec("node_graph.int", "result")
    assert "a" in task.inputs
    assert "b" in task.inputs
    assert "result" in task.outputs
