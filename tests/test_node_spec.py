import copy
import pytest
from types import SimpleNamespace
from node_graph.socket_spec import namespace as ns
from node_graph.node_spec import NodeSpec, hash_spec, BaseHandle
from node_graph.executor import RuntimeExecutor, SafeExecutor


def test_nodespec_serialize_roundtrip_embedded():
    """When the executor is a normal module function (not a BaseHandle),
    the spec persists in 'embedded' mode and round-trips via SafeExecutor.
    """
    inp = ns(x=int, y=(int, 2))
    out = ns(sum=int)

    ex = RuntimeExecutor(mode="module", module_path="math", callable_name="hypot")
    spec = NodeSpec(
        identifier="pkg.add",
        catalog="Math",
        inputs=inp,
        outputs=out,
        executor=ex,
        metadata={"k": "v"},
        version="1.0",
    )

    d = spec.to_dict()
    # Embedded mode stores schema
    assert d["mode"] == "embedded"
    assert "inputs" in d and "outputs" in d
    assert "error_handlers" not in d or d["error_handlers"] == {}

    spec2 = NodeSpec.from_dict(copy.deepcopy(d))

    # Core fields are preserved
    assert spec2.identifier == spec.identifier
    assert spec2.catalog == spec.catalog
    assert spec2.inputs == spec.inputs
    assert spec2.outputs == spec.outputs
    assert spec2.metadata == spec.metadata
    assert spec2.version == spec.version

    # Executor roundtrip uses SafeExecutor with same basic descriptor
    assert isinstance(spec2.executor, SafeExecutor)
    assert spec2.executor.mode == "module"
    assert spec2.executor.module_path == "math"
    assert spec2.executor.callable_name == "hypot"


def test_nodespec_to_dict_module_handle_strips_schema():
    """If the executor.callable is a BaseHandle, persistence mode is 'module_handle'
    and schema is not embedded in the dict.
    """

    # Build an inner spec (the one the handle wraps)
    inner = NodeSpec(
        identifier="inner.node",
        catalog="Test",
        inputs=ns(a=int),
        outputs=ns(b=int),
        metadata={"inner": True},
    )

    # Minimal handle that satisfies isinstance(x, BaseHandle)
    class DummyHandle(BaseHandle):
        def __init__(self, _spec):
            super().__init__(_spec, get_current_graph=lambda: None)

    handle = DummyHandle(inner)

    # Minimal executor that exposes .callable and .to_dict()
    class FakeExec:
        def __init__(self, callable):
            self.callable = callable

        def to_dict(self):
            # shape doesn't matter for this test, since we only test to_dict() of the spec
            return {"mode": "fake", "note": "not used in this test"}

    outer = NodeSpec(
        identifier="outer.node",
        catalog="Test",
        inputs=ns(x=int),  # These should NOT be serialized in module_handle mode
        outputs=ns(y=int),
        executor=FakeExec(handle),
        metadata={"k": "v"},
    )

    d = outer.to_dict()
    assert d["mode"] == "module_handle"
    # In module_handle mode, schema is omitted for compactness
    assert "inputs" not in d
    assert "outputs" not in d
    assert "error_handlers" not in d or d["error_handlers"] == {}
    # Executor must still be present
    assert "executor" in d and isinstance(d["executor"], dict)


def test_hash_spec_stability():
    inp = ns(x=int)
    out = ns(y=int)
    h1 = hash_spec("foo", inp, out)
    h2 = hash_spec("foo", inp, out)
    assert h1 == h2

    # change outputs changes hash
    out2 = ns(y=int, z=int)
    h3 = hash_spec("foo", inp, out2)
    assert h3 != h1

    # extra payload affects hash
    h4 = hash_spec("foo", inp, out, extra={"meta": 1})
    assert h4 != h1


def test_nodespec_resolve_base_class_default():
    # Default should be SpecNode (importable)
    s = NodeSpec(identifier="demo.id")
    Base = s._resolve_base_class()
    assert Base.__name__ == "SpecNode"


def test_nodespec_resolve_base_class_custom():
    s = NodeSpec(identifier="demo.id", base_class_path="builtins.object")
    Base = s._resolve_base_class()
    assert Base is object


def test_from_dict_module_handle_requires_executor_raises():
    d = {
        "mode": "module_handle",
        "identifier": "x.y",
        "catalog": "Test",
        # executor intentionally omitted
    }
    with pytest.raises(ValueError, match="requires an executor"):
        NodeSpec.from_dict(copy.deepcopy(d))


def test_from_dict_module_handle_with_non_handle_raises():
    # SafeExecutor will resolve to math.hypot (a normal function, not a BaseHandle)
    d = {
        "mode": "module_handle",
        "identifier": "x.y",
        "catalog": "Test",
        "executor": {"mode": "module", "module_path": "math", "callable_name": "hypot"},
    }
    with pytest.raises(TypeError, match="requires a decorated handle"):
        NodeSpec.from_dict(copy.deepcopy(d))


def test_from_dict_module_handle_with_handle_returns_inner_spec(monkeypatch):
    # Build the inner spec that the handle should return
    inner = NodeSpec(
        identifier="inner.node",
        catalog="Test",
        inputs=ns(a=int),
        outputs=ns(b=int),
        metadata={"inner": True},
    )

    class DummyHandle(BaseHandle):
        def __init__(self, _spec):
            super().__init__(_spec, get_current_graph=lambda: None)

    handle = DummyHandle(inner)

    # Monkeypatch SafeExecutor in the module under test so that
    # executor.callable is our DummyHandle instance
    def _dummy_safe_executor(**kwargs):
        return SimpleNamespace(callable=handle)

    monkeypatch.setattr("node_graph.node_spec.SafeExecutor", _dummy_safe_executor)

    d = {
        "mode": "module_handle",
        "identifier": "outer.node",
        "catalog": "Test",
        "executor": {"mode": "direct"},  # contents don't matter for the dummy
    }

    spec = NodeSpec.from_dict(copy.deepcopy(d))
    # Should return the *inner* spec directly
    assert spec is inner
    assert spec.identifier == "inner.node"
    assert spec.inputs.fields.keys() == inner.inputs.fields.keys()
    assert spec.outputs.fields.keys() == inner.outputs.fields.keys()


def test_from_dict_unrecognized_mode_raises():
    d = {
        "mode": "weird_mode",
        "identifier": "x.y",
        "catalog": "Test",
        "executor": {"mode": "module", "module_path": "math", "callable_name": "hypot"},
    }
    with pytest.raises(ValueError, match="unrecognized persistence_mode 'weird_mode'"):
        NodeSpec.from_dict(copy.deepcopy(d))
