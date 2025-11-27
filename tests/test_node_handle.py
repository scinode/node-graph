from node_graph.socket_spec import namespace as ns
from node_graph.task_spec import TaskSpec, TaskHandle
from node_graph.executor import RuntimeExecutor
from node_graph import socket_spec as ss
from node_graph.task import Task


def test_taskhandle_inputs_outputs_view():
    spec = TaskSpec(
        identifier="pkg.add",
        inputs=ns(x=int, y=int),
        outputs=ns(sum=int, product=int),
        executor=RuntimeExecutor(
            mode="module", module_path="math", callable_name="hypot"
        ),
        base_class=Task,
    )
    h = TaskHandle(spec)
    # views exist
    iv = h.inputs
    ov = h.outputs
    assert isinstance(iv, ss.SocketView)
    assert isinstance(ov, ss.SocketView)
    # selection works
    assert isinstance(iv.x, ss.SocketView)
    assert isinstance(ov.sum, ss.SocketView)


def test_taskhandle_call_flow():
    from node_graph.socket import TaskSocketNamespace

    def add(x, y):
        return x + y

    spec = TaskSpec(
        identifier="pkg.add",
        inputs=ns(x=int, y=int),
        outputs=ns(sum=int),
        executor=RuntimeExecutor.from_callable(add),
        base_class=Task,
    )
    h = TaskHandle(spec)

    # call with args & kwargs; the prepare_function_inputs will pack them
    out = h(3, y=4)  # returns FakeTask.outputs
    assert isinstance(out, TaskSocketNamespace)
    assert "sum" in out
