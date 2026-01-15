from __future__ import annotations
import pytest
from typing import Optional, Union
from node_graph import Graph, task


@task()
def add(x: int, y: int) -> int:
    return x + y


@task()
def multiply(x: float, y: float) -> float:
    return x * y


class DummyA:
    pass


class DummyB:
    pass


@task()
def take_a(x: DummyA) -> DummyA:
    return x


@task()
def take_b(x: DummyB) -> DummyB:
    return x


@task()
def take_a_optional(x: Optional[DummyA]) -> Optional[DummyA]:
    return x


@task()
def add_union(x: Union[int, float], y: Union[int, float]) -> Union[int, float]:
    return x + y


@task()
def add_union_pep604(x: int | float, y: int | float) -> int | float:
    return x + y


@task()
def multiply_int(x: int, y: int) -> int:
    return x * y


@pytest.fixture
def add_multiply_ng():
    ng = Graph()
    ng.add_task(add, "add1")
    ng.add_task(multiply, "multiply1")
    return ng


def test_link_another_graph(ng, ng_decorator):
    """Test link between two graph."""
    try:
        ng.add_link(ng.tasks["add1"].outputs[0], ng_decorator.tasks["add3"].inputs[1])
    except Exception as e:
        assert "Can not link sockets from different graphs" in str(e)


def test_max_link_limit(ng):
    # should raise a error when the link limit is reached.
    try:
        ng.add_link(ng.tasks["float1"].outputs[0], ng.tasks["add2"].inputs["y"])
    except Exception as e:
        assert (
            str(e)
            == "Socket add2.inputs.y: number of links 2 larger than the link limit 1."
        )


def test_clear(ng):
    """Test clear task graph."""
    ng.links.clear()
    assert len(ng.links) == 0
    assert len(ng.tasks["add1"].outputs[0]._links) == 0
    assert len(ng.tasks["add1"].inputs[0]._links) == 0


def test_repr(ng):
    """Test __repr__ method."""
    assert repr(ng.links) == "LinkCollection({} links)\n".format(len(ng.links))


def test_delete_link(ng):
    """Test delete task."""
    nlink = len(ng.links)
    del ng.links[[0, 1]]
    assert len(ng.links) == nlink - 2
    with pytest.raises(ValueError, match="Invalid index type for __delitem__: "):
        del ng.links[sum]


def test_equal_types_link_ok(add_multiply_ng):
    ng = add_multiply_ng
    ng.add_link(
        ng.tasks.add1.outputs.result, ng.tasks.multiply1.inputs.x
    )  # int -> float OK
    with pytest.raises(TypeError, match="Socket type mismatch:"):
        ng.add_link(
            ng.tasks.multiply1.outputs.result, ng.tasks.add1.inputs.x
        )  # float -> int NOK


def test_annotated_socket_match(add_multiply_ng):
    ng = add_multiply_ng
    ng.add_task(take_a, "take_a1")
    ng.add_task(take_a_optional, "take_a2")
    ng.add_task(take_b, "take_b1")

    ng.add_link(ng.tasks.take_a1.outputs.result, ng.tasks.take_a2.inputs.x)

    with pytest.raises(TypeError, match="Socket annotated type mismatch:"):
        ng.add_link(ng.tasks.take_a1.outputs.result, ng.tasks.take_b1.inputs.x)


def test_union_link_accepts_members():
    ng = Graph()
    ng.add_task(add_union, "add1")
    ng.add_task(add_union_pep604, "add2")
    ng.add_task(multiply_int, "multiply1")

    ng.add_link(ng.tasks.add1.outputs.result, ng.tasks.add2.inputs.x)
    ng.add_link(ng.tasks.add2.outputs.result, ng.tasks.multiply1.inputs.x)
