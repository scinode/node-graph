import copy
import pytest
from node_graph import socket_spec as ss
from node_graph.orm.mapping import type_mapping
from typing import Any, Annotated
from node_graph import node


def test_namespace_build_and_roundtrip():
    tm = type_mapping
    ns = ss.namespace(
        a=int,
        b=(int, 5),  # defaulted leaf
        c=ss.namespace(d=str),  # nested namespace
    )
    assert ns.identifier == tm["namespace"]
    assert set(ns.fields.keys()) == {"a", "b", "c"}
    assert ns.defaults == {"b": 5}
    assert ns.fields["c"].identifier == tm["namespace"]
    assert set(ns.fields["c"].fields.keys()) == {"d"}

    blob = ns.to_dict()
    ns2 = ss.SocketSpec.from_dict(copy.deepcopy(blob))
    assert ns2 == ns
    # ensure deep equals on nested
    assert ns2.fields["c"].fields["d"].identifier == type_mapping[str]


def test_dynamic_namespace_and_item_view():
    tm = type_mapping
    dyn = ss.dynamic(int, fixed1=str, fixed2=int)
    assert dyn.identifier == tm["namespace"]
    assert dyn.dynamic is True
    assert dyn.item is not None
    assert dyn.item.identifier == tm[int]
    assert set(dyn.fields.keys()) == {"fixed1", "fixed2"}

    view = ss.SocketView(dyn)
    assert isinstance(view.item, ss.SocketView)
    assert isinstance(view.fixed1, ss.SocketView)
    with pytest.raises(AttributeError):
        _ = view.missing


def test_expose_include_exclude_prefix_rename():
    base = ss.namespace(foo=int, bar=str, baz=int)
    # include/only
    inc = ss.expose(base, include=["foo", "baz"])
    assert set(inc.fields.keys()) == {"foo", "baz"}
    assert inc.defaults == {}

    only = base.only("bar")
    assert set(only.fields.keys()) == {"bar"}

    # exclude
    exc = base.exclude("bar")
    assert set(exc.fields.keys()) == {"foo", "baz"}

    exc = ss.expose(base, exclude=["bar"])
    assert set(exc.fields.keys()) == {"foo", "baz"}

    # prefix
    pfx = base.prefix("inp_")
    assert set(pfx.fields.keys()) == {"inp_foo", "inp_bar", "inp_baz"}

    exc = ss.expose(base, prefix="inp_")
    assert set(exc.fields.keys()) == {"inp_foo", "inp_bar", "inp_baz"}

    # rename (no collision)
    ren = base.rename({"foo": "x", "baz": "z"})
    assert set(ren.fields.keys()) == {"x", "bar", "z"}

    exc = ss.expose(base, rename={"foo": "x", "baz": "z"})
    assert set(exc.fields.keys()) == {"x", "bar", "z"}

    # rename collision
    with pytest.raises(ValueError):
        _ = base.rename({"foo": "bar"})  # would collide


def test_socketview_transform_chaining():
    base = ss.namespace(a=int, b=int, c=int)
    v = ss.SocketView(base).exclude("b").prefix("p_")
    spec = v.to_spec()
    assert set(spec.fields.keys()) == {"p_a", "p_c"}


def test_from_namespace_snapshot(monkeypatch):
    """
    Build a small live namespace shape and ensure `from_namespace` snapshots it.
    """
    from node_graph.socket import SocketMetadata

    # Fake socket classes with minimal surface
    class FakeLeaf:
        def __init__(self, name, ident="node_graph.any"):
            self._name = name
            self._identifier = ident

    class FakeNS:
        def __init__(self, name, sockets=None):
            self._name = name
            self._sockets = sockets or {}
            self._metadata = SocketMetadata()

    # live shape: ns { x: leaf, inner: ns{ y: leaf } }
    live = FakeNS(
        "inputs",
        sockets={
            "x": FakeLeaf("x", ident=type_mapping[int]),
            "inner": FakeNS(
                "inner", sockets={"y": FakeLeaf("y", ident=type_mapping[str])}
            ),
        },
    )

    # Monkeypatch NodeSocketNamespace type check expectation
    monkeypatch.setattr(ss, "NodeSocketNamespace", FakeNS, raising=False)
    monkeypatch.setattr(ss, "NodeSocket", FakeLeaf, raising=False)

    spec = ss.SocketSpec.from_namespace(live, role="input")
    assert spec.identifier == type_mapping["namespace"]
    assert set(spec.fields.keys()) == {"x", "inner"}
    assert spec.fields["x"].identifier == type_mapping[int]
    assert spec.fields["inner"].identifier == type_mapping["namespace"]
    assert spec.fields["inner"].fields["y"].identifier == type_mapping[str]


def test_merge_specs():
    from node_graph.socket_spec import merge_specs

    n1 = ss.namespace(a=int, b=int, c=int)
    n2 = ss.namespace(d=int, e=int)
    merged = merge_specs(n1, n2)
    assert set(merged.fields.keys()) == {"a", "b", "c", "d", "e"}


def test_build_inputs_from_signature():
    def add(x, y):
        return x + y

    with pytest.raises(TypeError, match="inputs must be a SocketSpec"):
        ss.BaseSpecInferAPI.build_inputs_from_signature(add, explicit=int)

    spec = ss.BaseSpecInferAPI.build_inputs_from_signature(
        add, explicit=ss.namespace(x=Any)
    )
    assert "x" in spec.fields

    with pytest.raises(TypeError, match="inputs must be a namespace"):
        spec = ss.BaseSpecInferAPI.build_inputs_from_signature(
            add, explicit=ss.SocketSpec("any")
        )


def test_build_outputs_from_signature():
    def add(x, y):
        return x + y

    with pytest.raises(TypeError, match="outputs must be a SocketSpec"):
        ss.BaseSpecInferAPI.build_outputs_from_signature(add, explicit=int)

    spec = ss.BaseSpecInferAPI.build_outputs_from_signature(
        add, explicit=ss.namespace()
    )
    assert "result" in spec.fields

    spec = ss.BaseSpecInferAPI.build_outputs_from_signature(
        add, explicit=ss.SocketSpec("any")
    )
    assert "result" in spec.fields


def test_validate_socket_data():

    with pytest.raises(TypeError, match="All elements in the list must be strings"):
        ss.validate_socket_data(["a", 2])
    with pytest.raises(TypeError, match="Expected list or namespace type"):
        ss.validate_socket_data({"a": 1})


def test_is_namespace():
    assert ss._is_namespace(ss.namespace())
    assert not ss._is_namespace(ss.SocketSpec("any"))


def test_expose_node_spec():
    from node_graph.socket import NodeSocket, NodeSocketNamespace

    @node()
    def test_calc(x: int) -> Annotated[dict, ss.namespace(square=int, double=int)]:
        return {"square": x * x, "double": x + x}

    @node(outputs=ss.namespace(sum=int, product=int))
    def add_multiply(data: Annotated[dict, ss.namespace(x=int, y=int)]) -> dict:
        return {"sum": data["x"] + data["y"], "product": data["x"] * data["y"]}

    @node.graph(
        outputs=ss.namespace(
            out1=add_multiply.outputs, out2=test_calc.outputs["square"]
        )
    )
    def test_graph(x: int, data: Annotated[dict, ss.namespace(y=int)]) -> dict:
        am = add_multiply(data={"x": x, "y": data["y"]})
        tc = test_calc(x)
        return {"out1": am, "out2": tc.square}

    ng = test_graph.build_graph(x=1, data={"y": 2})
    assert "sum" in ng.outputs.out1
    assert "out2" in ng.outputs
    assert isinstance(ng.outputs.out1, NodeSocketNamespace)
    assert isinstance(ng.outputs.out1.sum, NodeSocket)
    assert isinstance(ng.outputs.out2, NodeSocket)
