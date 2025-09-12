import copy
import pytest
from types import SimpleNamespace

from node_graph.socket_spec import namespace as ns
from node_graph.node_spec import NodeSpec, BaseHandle
from node_graph.executor import RuntimeExecutor, SafeExecutor


def test_nodespec_serialize_roundtrip_embedded():
    """Importable callable without decorator_path falls back to 'embedded' (safe)."""
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
    assert d["mode"] == "embedded"
    assert "inputs" in d and "outputs" in d

    spec2 = NodeSpec.from_dict(copy.deepcopy(d))
    assert spec2.identifier == spec.identifier
    assert spec2.catalog == spec.catalog
    assert spec2.inputs == spec.inputs
    assert spec2.outputs == spec.outputs
    assert spec2.metadata == spec.metadata
    assert spec2.version == spec.version
    assert isinstance(spec2.executor, SafeExecutor)
    assert spec2.executor.mode == "module"
    assert spec2.executor.module_path == "math"
    assert spec2.executor.callable_name == "hypot"
    assert spec2.mode == "embedded"


def test_nodespec_to_dict_module_handle_strips_schema():
    """If executor.callable is a BaseHandle, store compactly as 'module_handle'."""
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

    class FakeExec:
        def __init__(self, callable):
            self.callable = callable
            self.mode = "module"  # <-- make it importable

        def to_dict(self):
            return {
                "mode": "module"
            }  # shape consistent with SafeExecutor/RuntimeExecutor

    outer = NodeSpec(
        identifier="outer.node",
        catalog="Test",
        inputs=ns(x=int),
        outputs=ns(y=int),
        executor=FakeExec(handle),
        metadata={"k": "v"},
    )

    d = outer.to_dict()
    assert d["mode"] == "module_handle"
    assert "inputs" not in d and "outputs" not in d
    assert "executor" in d


def test_nodespec_resolve_base_class_default():
    # Default should be SpecNode (importable)
    s = NodeSpec(identifier="demo.id")
    bc = s._resolve_base_class()
    assert bc.__name__ == "SpecNode"


def test_nodespec_resolve_base_class_custom():
    s = NodeSpec(identifier="demo.id", base_class_path="builtins.object")
    bc = s._resolve_base_class()
    assert bc is object


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

    # SafeExecutor(**...) will return an object exposing .callable = handle
    def _dummy_safe_executor(**kwargs):
        return SimpleNamespace(callable=handle)

    monkeypatch.setattr("node_graph.node_spec.SafeExecutor", _dummy_safe_executor)

    d = {
        "mode": "module_handle",
        "identifier": "outer.node",
        "catalog": "Test",
        "executor": {"mode": "module"},  # contents ignored by our dummy
    }

    spec = NodeSpec.from_dict(copy.deepcopy(d))
    assert spec is inner
    assert spec.identifier == "inner.node"


def test_nodespec_resolve_decorator():
    from node_graph.decorator import node

    decorator = NodeSpec._resolve_decorator()
    assert decorator is node
    decorator = NodeSpec._resolve_decorator(decorator_path="builtins.object")
    assert decorator is object


def test_nodespec_to_dict_sets_decorator_build_when_importable_and_decorator_present():
    """If callable is importable and a decorator is provided, default to 'decorator_build'."""
    ex = RuntimeExecutor(mode="module", module_path="math", callable_name="hypot")
    spec = NodeSpec(
        identifier="decor.built",
        catalog="Math",
        executor=ex,
        decorator_path="dummy.module.node",  # presence triggers decorator_build
    )

    d = spec.to_dict()
    assert d["mode"] == "decorator_build"
    assert d.get("decorator_path") == "dummy.module.node"
    assert "inputs" not in d and "outputs" not in d


def test_from_dict_decorator_build_requires_executor_raises():
    d = {
        "mode": "decorator_build",
        "identifier": "x.y",
        "catalog": "Test",
        # no executor
    }
    with pytest.raises(ValueError, match="requires an executor"):
        NodeSpec.from_dict(copy.deepcopy(d))


def test_from_dict_decorator_build_rebuilds_via_decorator(monkeypatch):
    """Rebuild the spec using a decorator and an importable callable."""
    built = NodeSpec(
        identifier="built.via.decorator",
        catalog="Test",
        inputs=ns(a=int),
        outputs=ns(b=int),
        metadata={"rebuilt": True},
    )

    def dummy_decorator():
        def _apply(func):
            class H:
                def __init__(self, spec):
                    self._spec = spec

            return H(built)

        return _apply

    monkeypatch.setattr(
        NodeSpec,
        "_resolve_decorator",
        staticmethod(lambda decorator_path: dummy_decorator),
    )

    d = {
        "mode": "decorator_build",
        "identifier": "outer.node",
        "catalog": "Test",
        "decorator_path": "some.module.node",
        "executor": {"mode": "module", "module_path": "math", "callable_name": "hypot"},
    }

    spec = NodeSpec.from_dict(copy.deepcopy(d))
    assert isinstance(spec, NodeSpec)
    assert spec.identifier == "built.via.decorator"
    assert spec.inputs.fields.keys() == built.inputs.fields.keys()
    assert spec.outputs.fields.keys() == built.outputs.fields.keys()
    assert spec.metadata.get("rebuilt") is True


def test_from_dict_unrecognized_mode_raises():
    d = {
        "mode": "weird_mode",
        "identifier": "x.y",
        "catalog": "Test",
        "executor": {"mode": "module", "module_path": "math", "callable_name": "hypot"},
    }
    with pytest.raises(ValueError, match="unrecognized persistence_mode 'weird_mode'"):
        NodeSpec.from_dict(copy.deepcopy(d))


def test_is_module_handle_truth_table():
    inner = NodeSpec(identifier="inner", catalog="Test")

    class DummyHandle(BaseHandle):
        def __init__(self, _spec):
            super().__init__(_spec, get_current_graph=lambda: None)

    handle = DummyHandle(inner)

    class FakeExec:
        def __init__(self, callable):
            self.callable = callable

    spec_handle = NodeSpec(identifier="H", executor=FakeExec(handle))
    spec_func = NodeSpec(
        identifier="F",
        executor=RuntimeExecutor(
            mode="module", module_path="math", callable_name="hypot"
        ),
    )

    assert spec_handle.is_module_handle() is True
    assert spec_func.is_module_handle() is False


def test_to_dict_overrides_user_mode_to_embedded_when_not_importable():
    from node_graph.socket_spec import namespace as ns

    class FakeExec:
        def __init__(self):
            self.mode = "graph"  # not "module" -> not importable
            self.callable = lambda x: x

        def to_dict(self):
            return {"mode": "graph"}

    spec = NodeSpec(
        identifier="non.importable",
        inputs=ns(a=int),
        outputs=ns(b=int),
        executor=FakeExec(),
        metadata={"m": 1},
        mode="module_handle",  # user tries to force a compact mode
    )
    d = spec.to_dict()
    assert d["mode"] == "embedded"  # OVERRIDDEN
    assert "inputs" in d and "outputs" in d  # schema embedded


def test_to_dict_embedded_even_if_decorator_present_but_not_importable():
    from node_graph.socket_spec import namespace as ns

    class FakeExec:
        def __init__(self):
            self.mode = "graph"  # not importable
            self.callable = lambda x: x

        def to_dict(self):
            return {"mode": "graph"}

    spec = NodeSpec(
        identifier="non.importable.decorated",
        inputs=ns(a=int),
        outputs=ns(b=int),
        executor=FakeExec(),
        decorator_path="some.module.node",  # would suggest decorator_build, but not importable
    )
    d = spec.to_dict()
    assert d["mode"] == "embedded"
    assert "inputs" in d and "outputs" in d
