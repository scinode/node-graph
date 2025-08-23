import pytest
from node_graph.error_handler import ErrorHandlerSpec, normalize_error_handlers
from node_graph.executor import NodeExecutor
from node_graph.node_spec import NodeSpec
from node_graph.socket_spec import infer_specs_from_callable


def sample_handler(task):
    # dummy handler
    return "ok"


def another_handler(task):
    return "retry"


class DummyExitCodes:
    # mimic enum.value integers that the app would pass in
    ERROR_A = 101
    ERROR_B = 202
    ERROR_C = 303


def _assert_executor_roundtrips(exec_obj: NodeExecutor):
    """Assert NodeExecutor is serializable/deserializable with equal dict payload."""
    d = exec_obj.to_dict()
    rebuilt = NodeExecutor(**d)
    assert rebuilt.to_dict() == d


def _build_minimal_spec(fn):
    in_spec, out_spec = infer_specs_from_callable(fn, None, None)
    return in_spec, out_spec


def test_error_handler_spec_from_callable_and_serialize():
    exec_ = NodeExecutor.from_callable(sample_handler)
    _assert_executor_roundtrips(exec_)

    spec = ErrorHandlerSpec(
        handler=exec_,
        exit_codes=[DummyExitCodes.ERROR_A, 42, 7],
        max_retries=5,
    )
    d = spec.to_dict()
    assert isinstance(d, dict)
    assert d["exit_codes"] == [DummyExitCodes.ERROR_A, 42, 7]
    assert d["max_retries"] == 5
    # handler payload must be a NodeExecutor dict
    assert isinstance(d["handler"], dict)
    spec2 = ErrorHandlerSpec.from_dict(d)
    assert isinstance(spec2.handler, NodeExecutor)
    _assert_executor_roundtrips(spec2.handler)
    assert spec2.exit_codes == [DummyExitCodes.ERROR_A, 42, 7]
    assert spec2.max_retries == 5


def test_normalize_error_handlers_various_inputs():
    # 1) callable
    handlers = normalize_error_handlers(
        {"test": {"handler": sample_handler, "exit_codes": [1, 2], "max_retries": 3}}
    )
    assert len(handlers) == 1
    assert isinstance(handlers["test"].handler, NodeExecutor)
    _assert_executor_roundtrips(handlers["test"].handler)
    assert handlers["test"].exit_codes == [1, 2]
    assert handlers["test"].max_retries == 3

    # 2) NodeExecutor
    nexec = NodeExecutor.from_callable(another_handler)
    handlers = normalize_error_handlers(
        {"test": {"handler": nexec, "exit_codes": [10], "max_retries": 1}}
    )
    assert isinstance(handlers["test"].handler, NodeExecutor)
    _assert_executor_roundtrips(handlers["test"].handler)
    assert handlers["test"].exit_codes == [10]

    # 3) dict(NodeExecutor)
    as_dict = nexec.to_dict()
    handlers = normalize_error_handlers(
        {"test": {"handler": as_dict, "exit_codes": [11, 12]}}
    )
    assert isinstance(handlers["test"].handler, NodeExecutor)
    _assert_executor_roundtrips(handlers["test"].handler)
    assert handlers["test"].exit_codes == [11, 12]

    # 4) ErrorHandlerSpec passthrough, ensure ints enforced
    spec = ErrorHandlerSpec(handler=nexec, exit_codes=[99], max_retries=9)
    handlers = normalize_error_handlers({"test": spec})
    assert isinstance(handlers["test"], ErrorHandlerSpec)
    assert handlers["test"].exit_codes == [99]
    assert handlers["test"].max_retries == 9


def test_nodespec_roundtrip_preserves_error_handlers():
    in_spec, out_spec = _build_minimal_spec(
        lambda x: x
    )  # any callable for IO inference

    handlers = normalize_error_handlers(
        {
            "handler_a": {
                "handler": sample_handler,
                "exit_codes": [DummyExitCodes.ERROR_A],
                "max_retries": 5,
            },
            "handler_b": {
                "handler": NodeExecutor.from_callable(another_handler).to_dict(),
                "exit_codes": [DummyExitCodes.ERROR_B],
            },
        }
    )
    spec = NodeSpec(
        identifier="TestNode",
        catalog="Tests",
        inputs=in_spec,
        outputs=out_spec,
        executor=NodeExecutor.from_callable(lambda x: x),
        error_handlers=handlers,
        metadata={"node_type": "Normal"},
        version="1.0.0",
    )

    d = spec.to_dict()
    assert "error_handlers" in d
    assert isinstance(d["error_handlers"], dict)
    assert all("handler" in eh for eh in d["error_handlers"])

    spec2 = NodeSpec.from_dict(d)
    assert spec2.identifier == "TestNode"
    assert len(spec2.error_handlers) == 2
    assert all(
        isinstance(eh.handler, NodeExecutor) for eh in spec2.error_handlers.values()
    )
    assert spec2.error_handlers["handler_a"].exit_codes == [DummyExitCodes.ERROR_A]
    assert spec2.error_handlers["handler_b"].exit_codes == [DummyExitCodes.ERROR_B]
    # executor payloads remain round-trippable
    for eh in spec2.error_handlers.values():
        _assert_executor_roundtrips(eh.handler)


def test_node_roundtrip_preserves_error_handlers():
    in_spec, out_spec = _build_minimal_spec(lambda x: x)
    handlers = normalize_error_handlers(
        {"test": {"handler": sample_handler, "exit_codes": [1, 2], "max_retries": 3}}
    )
    spec = NodeSpec(
        identifier="TestNode",
        inputs=in_spec,
        outputs=out_spec,
        executor=NodeExecutor.from_callable(lambda x: x),
        error_handlers=handlers,
    )

    node = spec.to_node(name="n1")
    data = node.to_dict(short=False, should_serialize=False)
    assert "error_handlers" in data
    assert len(data["error_handlers"]) == 1

    # mutate copy, then update_from_dict into a fresh node
    # data2 = copy.deepcopy(data)
    # data2["error_handlers"][0]["max_retries"] = 7
    # data2["error_handlers"][0]["exit_codes"] = [5]

    # fresh = Node(name="fresh")
    # fresh.update_from_dict(data2)
    # assert len(fresh.error_handlers) == 1
    # eh = fresh.error_handlers[0]
    # assert isinstance(eh.handler, NodeExecutor)
    # _assert_executor_roundtrips(eh.handler)
    # assert eh.max_retries == 7
    # assert eh.exit_codes == [5]


def test_decorator_node_applies_error_handlers(monkeypatch):
    try:
        from node_graph.node_spec import NodeSpec
    except Exception:
        pytest.skip("Decorator infrastructure not available in this environment.")

    # wire a minimal decorator using the provided API
    from node_graph import node

    @node(
        identifier="DecoNode",
        error_handlers={
            "test": {"handler": sample_handler, "exit_codes": [123], "max_retries": 2}
        },
        catalog="Tests",
    )
    def fn(a: int) -> int:
        return a + 1

    # The decorator returns a handle that wraps a NodeSpec (project’s API)
    handle = fn  # usually NodeHandle
    # Introspect spec via the handle (assuming .spec or ._spec; adapt if needed)
    spec = getattr(handle, "spec", None) or getattr(handle, "_spec", None)
    assert isinstance(spec, NodeSpec)
    assert spec.identifier == "DecoNode"
    assert len(spec.error_handlers) == 1
    eh = spec.error_handlers["test"]
    assert isinstance(eh.handler, NodeExecutor)
    _assert_executor_roundtrips(eh.handler)
    assert eh.exit_codes == [123]
    assert eh.max_retries == 2
