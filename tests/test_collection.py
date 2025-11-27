import pytest
from node_graph.collection import TaskCollection, Collection
from node_graph.task import Task
from node_graph import Graph


def test_base_collection():
    """Test base collection."""
    ng = Graph(name="test_base_collection")
    coll = TaskCollection(graph=ng)
    coll.path = "builtins"
    task1 = Task(name="task1")
    task2 = Task(name="task2")
    # apend
    coll._append(task1)
    coll._append(task2)
    assert len(coll) == 2
    assert task1.graph == ng
    # copy
    ng1 = Graph(name="test_base_collection")
    coll1 = coll._copy(graph=ng1)
    assert len(coll1) == 2
    # delete
    coll._pop(task1.name)
    assert len(coll) == 1
    # get
    assert coll["task2"] == task2
    # get by uuid
    assert coll._get_by_uuid(task2.uuid) == task2
    # __repr__
    assert (
        repr(coll)
        == """TaskCollection(parent = "test_base_collection", tasks = ["task2"])"""
    )


def test_delete_items():
    coll = Collection()
    coll._items = {"a": 1, "b": 2, "c": 3, "d": 4}
    del coll[0]
    assert coll._items == {"b": 2, "c": 3, "d": 4}
    del coll[[1, 2]]
    assert coll._items == {"b": 2}
    with pytest.raises(ValueError, match="Invalid index type for __delitem__: "):
        del coll[sum]
    coll._pop(0)
    assert coll._items == {}
