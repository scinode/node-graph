from node_graph import TaskPool, Task
import pytest


def test_task_pool():
    assert "node_graph.test_enum_update" in TaskPool
    assert isinstance(TaskPool.node_graph.test_enum_update.load()(), Task)
    with pytest.raises(
        AttributeError,
        match="Namespace node_graph has no attribute 'test_add1'",
    ):
        TaskPool.node_graph.test_add1
