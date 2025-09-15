from node_graph.socket_spec import namespace as ns
from node_graph.node_spec import NodeSpec
from node_graph.executor import RuntimeExecutor
from node_graph import socket_spec as ss
from node_graph.node_spec import NodeHandle


def test_nodehandle_inputs_outputs_view():
    spec = NodeSpec(
        identifier="pkg.add",
        inputs=ns(x=int, y=int),
        outputs=ns(sum=int, product=int),
        executor=RuntimeExecutor(
            mode="module", module_path="math", callable_name="hypot"
        ),
    )
    h = NodeHandle(spec)
    # views exist
    iv = h.inputs
    ov = h.outputs
    assert isinstance(iv, ss.SocketView)
    assert isinstance(ov, ss.SocketView)
    # selection works
    assert isinstance(iv.x, ss.SocketView)
    assert isinstance(ov.sum, ss.SocketView)


def test_nodehandle_call_flow():
    from node_graph.socket import NodeSocketNamespace

    def add(x, y):
        return x + y

    spec = NodeSpec(
        identifier="pkg.add",
        inputs=ns(x=int, y=int),
        outputs=ns(sum=int),
        executor=RuntimeExecutor.from_callable(add),
    )
    h = NodeHandle(spec)

    # call with args & kwargs; the prepare_function_inputs will pack them
    out = h(3, y=4)  # returns FakeTask.outputs
    assert isinstance(out, NodeSocketNamespace)
    assert "sum" in out
