import copy
import pytest
from node_graph import socket_spec as ss
from node_graph.orm.mapping import type_mapping
from typing import Any, Annotated
from node_graph import node
from dataclasses import MISSING


def test_namespace_build_and_roundtrip():
    tm = type_mapping
    ns = ss.namespace(
        a=int,
        b=(int, 5),  # defaulted leaf
        c=ss.namespace(d=str),  # nested namespace
    )
    assert ns.identifier == tm["namespace"]
    assert set(ns.fields.keys()) == {"a", "b", "c"}
    assert ns.fields["b"].default == 5
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


def test_select_include_exclude_prefix_rename():
    base = ss.namespace(foo=int, bar=str, baz=int)

    # include ("only") - keep a subset
    inc_wrapper = ss.namespace(
        x=Annotated[dict, base, ss.SocketSpecSelect(include=["foo", "baz"])]
    )
    inc = inc_wrapper.fields["x"]
    assert set(inc.fields.keys()) == {"foo", "baz"}

    # exclude - drop a subset
    exc_wrapper = ss.namespace(
        x=Annotated[dict, base, ss.SocketSpecSelect(exclude=["bar"])]
    )
    exc = exc_wrapper.fields["x"]
    assert set(exc.fields.keys()) == {"foo", "baz"}

    # prefix - rename all top-level keys with a prefix
    pfx_wrapper = ss.namespace(
        x=Annotated[dict, base, ss.SocketSpecSelect(prefix="inp_")]
    )
    pfx = pfx_wrapper.fields["x"]
    assert set(pfx.fields.keys()) == {"inp_foo", "inp_bar", "inp_baz"}

    # rename (no collision)
    ren_wrapper = ss.namespace(
        x=Annotated[dict, base, ss.SocketSpecSelect(rename={"foo": "x", "baz": "z"})]
    )
    ren = ren_wrapper.fields["x"]
    assert set(ren.fields.keys()) == {"x", "bar", "z"}


def test_select_rename_collision_raises():
    base = ss.namespace(foo=int, bar=str)
    with pytest.raises(ValueError):
        _ = ss.namespace(
            x=Annotated[dict, base, ss.SocketSpecSelect(rename={"foo": "bar"})]
        )


def test_dotted_include_exclude():
    base = ss.namespace(
        pw=ss.namespace(structure=int, kpoints=int, parameters=int),
        bands=ss.namespace(pw=ss.namespace(structure=int, kpoints=int)),
    )

    # EXCLUDE a nested path
    exc_wrapper = ss.namespace(
        x=Annotated[dict, base, ss.SocketSpecSelect(exclude="pw.structure")]
    )
    exc = exc_wrapper.fields["x"]
    assert "structure" not in exc.fields["pw"].fields
    assert "kpoints" in exc.fields["pw"].fields
    assert "parameters" in exc.fields["pw"].fields

    # INCLUDE a nested path (keeps only the selected branches)
    inc_wrapper = ss.namespace(
        x=Annotated[
            dict,
            base,
            ss.SocketSpecSelect(include=("pw.kpoints", "bands.pw.structure")),
        ]
    )
    inc = inc_wrapper.fields["x"]
    assert set(inc.fields.keys()) == {"pw", "bands"}
    assert set(inc.fields["pw"].fields.keys()) == {"kpoints"}
    assert set(inc.fields["bands"].fields.keys()) == {"pw"}
    assert set(inc.fields["bands"].fields["pw"].fields.keys()) == {"structure"}


def test_meta_overlay_required_is_metadata():
    base = ss.namespace(foo=int, bar=int)

    wrapped = ss.namespace(
        x=Annotated[
            dict,
            base,
            ss.SocketSpecMeta(required=True, is_metadata=True, help="top-level ns"),
        ]
    ).fields["x"]

    assert wrapped.meta.required is True
    assert wrapped.meta.is_metadata is True
    assert wrapped.meta.help == "top-level ns"


def test_include_prefix_exclude_prefix_top_level_only():
    base = ss.namespace(alpha=int, beta=int, gamma=int, band_k=int, band_e=int)

    # include all top-level fields starting with 'band_'
    inc_pfx = ss.namespace(
        x=Annotated[dict, base, ss.SocketSpecSelect(include_prefix="band_")]
    ).fields["x"]
    assert set(inc_pfx.fields.keys()) == {"band_k", "band_e"}

    # exclude all top-level fields starting with 'ba'
    exc_pfx = ss.namespace(
        x=Annotated[dict, base, ss.SocketSpecSelect(exclude_prefix="b")]
    ).fields["x"]
    # 'beta', 'band_k', 'band_e' removed; 'alpha', 'gamma' remain
    assert set(exc_pfx.fields.keys()) == {"alpha", "gamma"}


def test_socketview_traversal_only():
    base = ss.namespace(a=int, b=ss.namespace(c=int), d=int)

    v = ss.SocketView(base)
    # traverse to nested namespace 'b' and its child 'c'
    vb = v.b
    assert isinstance(vb, ss.SocketView)
    vb_spec = vb.to_spec()
    assert isinstance(vb_spec, ss.SocketSpec)
    assert set(vb_spec.fields.keys()) == {"c"}

    # unknown attribute raises
    with pytest.raises(AttributeError):
        _ = v.unknown_field

    # '.item' invalid on non-dynamic namespaces
    with pytest.raises(AttributeError):
        _ = v.item


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

    # if user provides a namespace explicitly, we use it directly
    # do NOT add a 'result' field
    spec = ss.BaseSpecInferAPI.build_outputs_from_signature(
        add, explicit=ss.namespace()
    )
    assert "result" not in spec.fields
    # will wrap the spec into a namespace with 'result' field
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
    assert ss.namespace().is_namespace()
    assert not ss.SocketSpec("any").is_namespace()


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

    ng = test_graph.build(x=1, data={"y": 2})
    assert "sum" in ng.outputs.out1
    assert "out2" in ng.outputs
    assert isinstance(ng.outputs.out1, NodeSocketNamespace)
    assert isinstance(ng.outputs.out1.sum, NodeSocket)
    assert isinstance(ng.outputs.out2, NodeSocket)


def test_default():
    ns = ss.namespace(
        a=int,
        b=(int, 5),
        c=ss.namespace(d=str),
    )
    ns1 = ss.set_default(ns, "b", 10)
    assert ns1.fields["b"].default == 10
    ns2 = ss.unset_default(ns1, "b")
    assert isinstance(ns2.fields["b"].default, type(MISSING))
    n3 = ss.set_default(ns2, "c.d", 10)
    assert n3.fields["c"].fields["d"].default == 10

    with pytest.raises(TypeError, match="Cannot set default on a namespace."):
        ss.set_default(ns, "c", 10)

    with pytest.raises(TypeError, match="Path passes through a leaf."):
        ss.unset_default(ns, "b.c")


def test_set_default_from_annotation():
    def add(a, b: Annotated[dict, ss.namespace(x=int, y=int)] = {"x": 1, "y": 2}):
        return a + b

    ns = ss.BaseSpecInferAPI.build_inputs_from_signature(add)
    assert ns.fields["b"].fields["x"].default == 1
    assert ns.fields["b"].fields["y"].default == 2

    def add(a, b: Annotated[dict, ss.namespace(x=int, y=int)] = 1):
        return a + b

    with pytest.raises(
        TypeError, match="Scalar default provided for namespace parameter"
    ):
        ns = ss.BaseSpecInferAPI.build_inputs_from_signature(add)

    def add(
        a,
        b: Annotated[dict, ss.namespace(x=int, y=ss.namespace(z=int))] = {
            "x": 1,
            "y": {"z": 2},
        },
    ):
        return a + b

    ns = ss.BaseSpecInferAPI.build_inputs_from_signature(add)
    assert ns.fields["b"].fields["x"].default == 1
    assert ns.fields["b"].fields["y"].fields["z"].default == 2

    def add(
        a,
        b: Annotated[dict, ss.namespace(x=int, y=ss.namespace(z=int))] = {
            "x": 1,
            "y": 1,
        },
    ):
        return a + b

    with pytest.raises(
        TypeError, match="Default for 'y' is scalar, but the field is a namespace."
    ):
        ns = ss.BaseSpecInferAPI.build_inputs_from_signature(add)
