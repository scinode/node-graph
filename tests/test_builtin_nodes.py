import pytest
from node_graph import Graph
from node_graph.socket_spec import namespace as ns
from node_graph.tasks.tests import test_add


def test_builtin_tasks() -> None:
    """Test builtin tasks of a task graph."""
    ng = Graph(inputs=ns(x=int, y=int), outputs=ns(result=int))
    assert len(ng.tasks) == 3
    assert ng.inputs._metadata.dynamic is False
    assert ng.outputs._metadata.dynamic is False
    assert ng.ctx._metadata.dynamic is True
    assert ng.ctx._metadata.child_default_link_limit == 1000000
    assert len(ng.inputs) == 2
    assert len(ng.outputs) == 1


def test_ctx() -> None:
    """Test the ctx of a task graph."""
    from node_graph.socket import TaskSocketNamespace

    ng = Graph(name="test_ctx")
    ng.ctx = {"x": 1.0, "y": 2.0}
    task1 = ng.add_task(test_add, "add1", x=1, y=ng.ctx.y)
    ng.ctx.sum = task1.outputs.result
    task2 = ng.add_task(test_add, "add2", x=2, y=task1.outputs.result)
    ng.ctx.sum = task2.outputs.result
    assert len(ng.ctx.sum._links) == 2
    # assign a namespace socket to the ctx
    ng.ctx.task1 = task1.outputs
    assert isinstance(ng.ctx.task1, TaskSocketNamespace)


def test_link() -> None:
    """Test the group inputs and outputs of a task graph."""
    ng = Graph(name="test_inputs_outputs")
    ng.inputs = {"x": 1.0, "y": 2.0}
    task1 = ng.add_task(test_add, "add1", x=ng.inputs.x)
    ng.add_task(
        test_add,
        "add2",
        x=ng.inputs.y,
        y=task1.outputs.result,
    )
    ng.outputs.sum = ng.tasks.add2.outputs.result
    assert len(ng.tasks) == 5
    assert len(ng.links) == 4


def test_from_dict() -> None:
    """Test the group inputs and outputs of a task graph."""
    ng = Graph(
        name="test_inputs_outputs",
        inputs=ns(x=float),
        outputs=ns(sum1=float, sum2=float),
    )
    ng.inputs = {"x": 1.0}
    ng.ctx = {"y": 2.0}
    task1 = ng.add_task(test_add, "add1", x=ng.inputs.x)
    ng.ctx.sum1 = task1.outputs.result
    ng.outputs.sum1 = ng.ctx.sum1
    ng.add_task(
        test_add,
        "add2",
        x=ng.ctx.y,
        y=task1.outputs.result,
    )
    ng.outputs.sum2 = ng.tasks.add2.outputs.result
    assert len(ng.links) == 6
    ng.to_dict()
    ng1 = Graph.from_dict(ng.to_dict())
    assert len(ng1.tasks) == 5
    assert len(ng1.links) == 6
    assert ng1.ctx.y.value == 2.0
    # add non-existing input will raise an error
    with pytest.raises(ValueError, match="Invalid assignment into namespace socket:"):
        ng1.inputs.z = 3.0


def test_from_dict_dynamic_inputs_outputs() -> None:
    """Test the group inputs and outputs of a task graph."""
    ng = Graph(name="test_inputs_outputs")
    ng.inputs = {"x": 1.0}
    ng.ctx = {"y": 2.0}
    task1 = ng.add_task(test_add, "add1", x=ng.inputs.x)
    ng.ctx.sum1 = task1.outputs.result
    ng.outputs.sum1 = ng.ctx.sum1
    ng.add_task(
        test_add,
        "add2",
        x=ng.ctx.y,
        y=task1.outputs.result,
    )
    ng.outputs.sum2 = ng.tasks.add2.outputs.result
    assert len(ng.links) == 6
    ng.to_dict()
    ng1 = Graph.from_dict(ng.to_dict())
    assert len(ng1.tasks) == 5
    assert len(ng1.links) == 6
    assert ng1.ctx.y.value == 2.0
    # add non-existing input will not raise an error
    ng1.inputs.z = 3.0
