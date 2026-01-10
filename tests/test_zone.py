from node_graph import Graph, task
from node_graph.manager import If, While, Zone
from node_graph.tasks.tests import test_add


@task()
def smaller_than(x, y):
    return x < y


@task()
def is_even(x):
    return x % 2 == 0


def _find_link(graph, from_task, to_task, to_socket_name):
    for link in graph.links:
        if (
            link.from_task == from_task
            and link.to_task == to_task
            and link.to_socket._scoped_name == to_socket_name
        ):
            return link
    return None


def test_zone_context_manager_children():
    with Graph("zone_context"):
        with Zone() as zone:
            out1 = test_add(x=1, y=2)
            out2 = test_add(x=out1.result, y=3)

        task1 = out1._task
        task2 = out2._task

    assert zone.spec.task_type == "ZONE"
    assert task1.parent == zone
    assert task2.parent == zone
    assert {child.name for child in zone.children} == {task1.name, task2.name}


def test_if_zone_sets_condition_link_and_children():
    with Graph("if_zone") as graph:
        base = test_add(x=1, y=2)
        condition = smaller_than(base.result, 5).result
        with If(condition, invert_condition=True) as if_zone:
            inner = test_add(x=base.result, y=10)

    assert if_zone.spec.task_type == "IF"
    assert if_zone.inputs["invert_condition"].value is True
    assert _find_link(
        graph, condition._task, if_zone, "conditions"
    ), "Missing link into if-zone condition input."
    assert inner._task.parent == if_zone


def test_while_zone_nesting_and_inputs():
    with Graph("while_zone") as graph:
        seed = test_add(x=1, y=1)
        condition = smaller_than(seed.result, 10).result
        with While(condition, max_iterations=3) as while_zone:
            even_cond = is_even(seed.result).result
            with If(even_cond) as if_zone:
                inner = test_add(x=seed.result, y=1)
            outer = test_add(x=seed.result, y=2)

    assert while_zone.spec.task_type == "WHILE"
    assert while_zone.inputs["max_iterations"].value == 3
    assert _find_link(
        graph, condition._task, while_zone, "conditions"
    ), "Missing link into while-zone condition input."
    assert if_zone.parent == while_zone
    assert even_cond._task.parent == while_zone
    assert inner._task.parent == if_zone
    assert outer._task.parent == while_zone
    assert {child.name for child in while_zone.children} == {
        if_zone.name,
        even_cond._task.name,
        outer._task.name,
    }
