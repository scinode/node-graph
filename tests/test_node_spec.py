import copy
import pytest
from types import SimpleNamespace

from node_graph.socket_spec import namespace as ns
from node_graph.node_spec import (
    NodeSpec,
    BaseHandle,
    SCHEMA_SOURCE_EMBEDDED,
    SCHEMA_SOURCE_CALLABLE,
)
from node_graph.executor import RuntimeExecutor, SafeExecutor
from node_graph.node import Node


def test_nodespec_serialize_roundtrip_embedded():
    """Importable callable without decorator_path falls back to 'embedded' (safe)."""
    inp = ns(x=int, y=(int, 2))
    out = ns(sum=int)
    ex = RuntimeExecutor(mode="module", module_path="math", callable_name="sqrt")

    spec = NodeSpec(
        identifier="pkg.add",
        catalog="Math",
        inputs=inp,
        outputs=out,
        executor=ex,
        metadata={"k": "v"},
        version="1.0",
        base_class=Node,
    )
    d = spec.to_dict()
    assert d["schema_source"] == SCHEMA_SOURCE_EMBEDDED
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
    assert spec2.executor.callable_name == "sqrt"
    assert spec2.schema_source == SCHEMA_SOURCE_EMBEDDED


def test_nodespec_to_dict_module_handle_strips_schema():
    """If executor.callable is a BaseHandle, store compactly as 'module_handle'."""
    inner = NodeSpec(
        identifier="inner.node",
        catalog="Test",
        inputs=ns(a=int),
        outputs=ns(b=int),
        metadata={"inner": True},
        base_class=Node,
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
                "schema_source": "module"
            }  # shape consistent with SafeExecutor/RuntimeExecutor

    outer = NodeSpec(
        identifier="outer.node",
        schema_source=SCHEMA_SOURCE_CALLABLE,
        catalog="Test",
        inputs=ns(x=int),
        outputs=ns(y=int),
        executor=FakeExec(handle),
        metadata={"k": "v"},
        base_class=Node,
    )

    d = outer.to_dict()
    assert d["schema_source"] == SCHEMA_SOURCE_CALLABLE
    assert "inputs" not in d and "outputs" not in d
    assert "executor" in d


def test_validate_base_class_path_required():

    with pytest.raises(
        ValueError, match="Either base_class or base_class_path must be provided."
    ):
        NodeSpec(identifier="demo.id")


def test_nodespecget_base_class_custom():
    s = NodeSpec(identifier="demo.id", base_class_path="builtins.object")
    bc = s.get_base_class(s.base_class_path)
    assert bc is object


def test_from_dict_callable_requires_executor_raises():
    d = {
        "schema_source": "callable",
        "identifier": "x.y",
        "catalog": "Test",
        # executor intentionally omitted
        "base_class_path": "node_graph.node.Node",
    }
    with pytest.raises(ValueError, match="requires an executor"):
        NodeSpec.from_dict(copy.deepcopy(d))


def test_from_dict_callable_basehandler(monkeypatch):
    # Build the inner spec that the handle should return
    inner = NodeSpec(
        identifier="inner.node",
        catalog="Test",
        inputs=ns(a=int),
        outputs=ns(b=int),
        metadata={"inner": True},
        base_class=Node,
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
        "schema_source": SCHEMA_SOURCE_CALLABLE,
        "identifier": "outer.node",
        "catalog": "Test",
        "executor": {},  # contents ignored by our dummy
        "base_class_path": "node_graph.node.Node",
    }

    spec = NodeSpec.from_dict(copy.deepcopy(d))
    assert spec is inner
    assert spec.identifier == "inner.node"


def test_from_dict_unrecognized_mode_raises():
    d = {
        "schema_source": "weird_mode",
        "identifier": "x.y",
        "base_class_path": "node_graph.node.Node",
    }
    with pytest.raises(ValueError, match="unrecognized schema_source 'weird_mode'"):
        NodeSpec.from_dict(copy.deepcopy(d))
