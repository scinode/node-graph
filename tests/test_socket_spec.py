import copy
import pytest
from node_graph import socket_spec as ss
from node_graph.orm.mapping import type_mapping
from typing import Any, Annotated
from node_graph import node
from dataclasses import dataclass, MISSING
from pydantic import BaseModel
from node_graph.materialize import runtime_meta_from_spec


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


def test_dynamic_namespace_without_item_type():
    tm = type_mapping
    dyn = ss.dynamic()
    assert dyn.identifier == tm["namespace"]
    assert dyn.dynamic is True
    assert dyn.item is None

    meta = runtime_meta_from_spec(dyn, role="input")
    assert meta.extras["item"] is None


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
            ss.SocketMeta(required=True, is_metadata=True, help="top-level ns"),
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

    # exclude all top-level fields starting with 'b'
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


def test_normalize_explicit_spec():
    spec = ss.namespace(foo=int, bar=int)
    ss._normalize_explicit_spec(spec) is spec
    ss._normalize_explicit_spec(ss.SocketView(spec)) is spec

    # Pydantic model
    class MyModel(BaseModel):
        foo: int
        bar: int

    spec = ss._normalize_explicit_spec(MyModel)
    assert isinstance(spec, ss.SocketSpec)
    assert set(spec.fields.keys()) == {"foo", "bar"}

    # Dataclass model
    @dataclass
    class MyDC:
        foo: int
        bar: int

    spec = ss._normalize_explicit_spec(MyDC)
    assert isinstance(spec, ss.SocketSpec)
    assert set(spec.fields.keys()) == {"foo", "bar"}


def test_build_inputs_from_explicit():
    def add(x, y):
        return x + y

    with pytest.raises(
        TypeError,
        match=r"Unsupported explicit spec\.",  # keep message flexible
    ):
        ss.SocketSpecAPI.build_inputs_from_signature(add, explicit=int)

    spec = ss.SocketSpecAPI.build_inputs_from_signature(
        add, explicit=ss.namespace(x=Any)
    )
    assert "x" in spec.fields

    with pytest.raises(TypeError, match="inputs must be a namespace"):
        _ = ss.SocketSpecAPI.build_inputs_from_signature(
            add, explicit=ss.SocketSpec("any")
        )

    # pydantic model
    class AddInputs(BaseModel):
        x: int
        y: int

    spec = ss.SocketSpecAPI.build_inputs_from_signature(add, explicit=AddInputs)
    assert "x" in spec.fields
    assert "y" in spec.fields

    # dataclass model
    @dataclass
    class AddInputsDC:
        x: int
        y: int

    spec = ss.SocketSpecAPI.build_inputs_from_signature(add, explicit=AddInputsDC)
    assert "x" in spec.fields
    assert "y" in spec.fields


def test_build_outputs_from_explicit():
    def add(x, y):
        return x + y

    with pytest.raises(
        TypeError,
        match=r"Unsupported explicit spec\.",
    ):
        ss.SocketSpecAPI.build_outputs_from_signature(add, explicit=int)

    # if user provides a namespace explicitly, we use it directly
    # do NOT add a 'result' field
    spec = ss.SocketSpecAPI.build_outputs_from_signature(add, explicit=ss.namespace())
    assert "result" not in spec.fields
    # will wrap the spec into a namespace with 'result' field
    spec = ss.SocketSpecAPI.build_outputs_from_signature(
        add, explicit=ss.SocketSpec("any")
    )
    assert "result" in spec.fields

    # pydantic model
    class AddOutputs(BaseModel):
        result: int

    spec = ss.SocketSpecAPI.build_outputs_from_signature(add, explicit=AddOutputs)
    assert "result" in spec.fields

    # dataclass model
    @dataclass
    class AddOutputsDC:
        result: int

    spec = ss.SocketSpecAPI.build_outputs_from_signature(add, explicit=AddOutputsDC)
    assert "result" in spec.fields


def test_build_inputs_from_annotation():
    def add(a, b: Annotated[dict, ss.namespace(x=int, y=int)]):
        """"""

    spec = ss.SocketSpecAPI.build_inputs_from_signature(add, explicit=None)
    assert "a" in spec.fields
    assert "x" in spec.fields["b"].fields

    # pydantic model
    class AddInputs(BaseModel):
        x: int
        y: int

    def add(a: AddInputs, b: Annotated[dict, AddInputs]):
        """"""

    spec = ss.SocketSpecAPI.build_inputs_from_signature(add, explicit=None)
    assert "a" in spec.fields
    assert "x" in spec.fields["a"].fields
    assert "b" in spec.fields
    assert "x" in spec.fields["b"].fields

    # dataclass model
    @dataclass
    class AddInputsDC:
        x: int
        y: int

    def add_dc(a: AddInputsDC, b: Annotated[dict, AddInputsDC]):
        """"""

    spec = ss.SocketSpecAPI.build_inputs_from_signature(add_dc, explicit=None)
    assert "a" in spec.fields
    assert "x" in spec.fields["a"].fields
    assert "b" in spec.fields
    assert "x" in spec.fields["b"].fields


def test_build_outputs_from_annotation():
    def add() -> Annotated[dict, ss.namespace(sum=int, product=int)]:
        """"""
        return {"sum": 0, "product": 0}

    spec = ss.SocketSpecAPI.build_outputs_from_signature(add, explicit=None)
    assert "sum" in spec.fields
    assert "sum" in spec.fields

    # pydantic model
    class AddOutputs(BaseModel):
        sum: int
        product: int

    def add_pm() -> AddOutputs:
        """"""
        return {"sum": 0, "product": 0}

    spec = ss.SocketSpecAPI.build_outputs_from_signature(add_pm, explicit=None)
    assert "sum" in spec.fields
    assert "product" in spec.fields

    # dataclass model
    @dataclass
    class AddOutputsDC:
        sum: int
        product: int

    def add_dc() -> AddOutputsDC:
        """"""
        return AddOutputsDC(0, 0)

    spec = ss.SocketSpecAPI.build_outputs_from_signature(add_dc, explicit=None)
    assert "sum" in spec.fields
    assert "product" in spec.fields


def test_validate_socket_data():
    with pytest.raises(TypeError, match="All elements in the list must be strings"):
        ss.validate_socket_data(["a", 2])
    with pytest.raises(TypeError, match="Unsupported spec input type:"):
        ss.validate_socket_data({"a": 1})

    # dataclass accepted
    @dataclass
    class VDC:
        a: int
        b: int

    spec = ss.validate_socket_data(VDC)
    assert isinstance(spec, ss.SocketSpec)
    assert set(spec.fields.keys()) == {"a", "b"}


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

    ns = ss.SocketSpecAPI.build_inputs_from_signature(add)
    assert ns.fields["b"].fields["x"].default == 1
    assert ns.fields["b"].fields["y"].default == 2

    def add2(a, b: Annotated[dict, ss.namespace(x=int, y=int)] = 1):
        return a + b

    with pytest.raises(
        TypeError, match="Scalar default provided for namespace parameter"
    ):
        _ = ss.SocketSpecAPI.build_inputs_from_signature(add2)

    def add3(
        a,
        b: Annotated[dict, ss.namespace(x=int, y=ss.namespace(z=int))] = {
            "x": 1,
            "y": {"z": 2},
        },
    ):
        return a + b

    ns = ss.SocketSpecAPI.build_inputs_from_signature(add3)
    assert ns.fields["b"].fields["x"].default == 1
    assert ns.fields["b"].fields["y"].fields["z"].default == 2

    def add4(
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
        _ = ss.SocketSpecAPI.build_inputs_from_signature(add4)


def test_add_spec_field():
    from node_graph.socket_spec import add_spec_field

    with pytest.raises(TypeError, match="expects a namespace SocketSpec at the root."):
        add_spec_field(ss.SocketSpec("any"), "a", ss.SocketSpec("any"))

    ns = ss.namespace(a=int, b=(int, 5))

    with pytest.raises(ValueError, match="Field name must be a non-empty string."):
        add_spec_field(ns, "", ss.SocketSpec("any"))

    ns1 = add_spec_field(ns, "c", ss.namespace(d=str))
    assert "c" in ns1.fields
    # nested
    ns2 = add_spec_field(ns1, "c.f", ss.namespace(g=str))
    assert "f" in ns2.fields["c"].fields
    # missing field
    with pytest.raises(ValueError, match="Cannot add"):
        add_spec_field(ns1, "e.f", ss.namespace(g=str))
    # not namespace
    with pytest.raises(TypeError, match="Cannot descend into non-namespace field"):
        add_spec_field(ns1, "a.f", ss.namespace(g=str))
    # already exist
    with pytest.raises(ValueError, match="Field 'c' already exists."):
        add_spec_field(ns1, "c", ss.namespace(g=str))


def test_remove_spec_field():
    from node_graph.socket_spec import remove_spec_field

    with pytest.raises(TypeError, match="expects a namespace SocketSpec at the root."):
        remove_spec_field(ss.SocketSpec("any"), "a")

    ns = ss.namespace(
        a=int,
        b=(int, 5),
        c=ss.namespace(d=str),
        d=int,
    )
    ns1 = remove_spec_field(ns, "b")
    assert "b" not in ns1.fields
    # multiple names
    ns2 = remove_spec_field(ns, ["a", "b"])
    assert "a" not in ns2.fields
    assert "b" not in ns2.fields


def test_pydantic_model():
    class Inner(BaseModel):
        d: str

    class Outer(BaseModel):
        a: int
        b: int = 5
        c: Inner

    ns = ss.from_model(Outer)

    assert ns.is_namespace()
    assert set(ns.fields.keys()) == {"a", "b", "c"}
    assert ns.fields["b"].default == 5
    assert ns.fields["c"].is_namespace()
    assert set(ns.fields["c"].fields.keys()) == {"d"}

    blob = ns.to_dict()
    ns2 = ss.SocketSpec.from_dict(copy.deepcopy(blob))
    assert ns2 == ns


def test_dynamic_pydantic_model():
    class Squares(BaseModel):
        model_config = {"extra": "allow"}

    result = ss.from_model(Squares)
    assert result.dynamic is True
    assert result.item.identifier == "node_graph.any"

    class Squares2(BaseModel):
        model_config = {"extra": "allow", "item_type": int}
        total: int

    result = ss.from_model(Squares2)
    assert result.dynamic is True
    assert "total" in result.fields
    assert result.item.identifier == "node_graph.int"


def test_mixed_annotation_and_model():
    class Row(BaseModel):
        sum: int
        product: int

    spec = ss.namespace(x=int, y=Row)
    assert spec.fields["y"].is_namespace()
    assert set(spec.fields["y"].fields.keys()) == {"sum", "product"}

    spec = ss.dynamic(Row, fixed1=str)
    assert spec.fields["fixed1"].identifier == "node_graph.string"
    assert spec.item.is_namespace()
    assert spec.dynamic is True
    assert set(spec.item.fields.keys()) == {"sum", "product"}


def test_leaf_pydantic_model():
    class MySpec(BaseModel):
        model_config = {"leaf": True}
        x: int
        y: int

    spec = ss.from_model(MySpec)
    assert not spec.is_namespace()

    # Per-use leaf wrapper (even if model had no flag)
    class Other(BaseModel):
        a: int
        b: int

    spec = ss.from_model(ss.Leaf[Other])
    assert not spec.is_namespace()


def test_dataclass_model_namespace_and_roundtrip():
    @dataclass
    class InnerDC:
        d: str

    @dataclass
    class OuterDC:
        a: int
        b: int = 5
        c: InnerDC = None

    ns = ss.from_model(OuterDC)
    assert ns.is_namespace()
    assert set(ns.fields.keys()) == {"a", "b", "c"}
    assert ns.fields["b"].default == 5
    assert ns.fields["c"].is_namespace()
    assert set(ns.fields["c"].fields.keys()) == {"d"}

    blob = ns.to_dict()
    ns2 = ss.SocketSpec.from_dict(copy.deepcopy(blob))
    assert ns2 == ns


def test_dynamic_dataclass_model():
    @dataclass
    class SquaresDC:
        model_config = {"extra": "allow"}  # dynamic
        # (no fixed fields)

    result = ss.from_model(SquaresDC)
    assert result.dynamic is True
    assert result.item.identifier == "node_graph.any"

    @dataclass
    class Squares2DC:
        model_config = {"extra": "allow", "item_type": int}
        total: int = 0

    result = ss.from_model(Squares2DC)
    assert result.dynamic is True
    assert "total" in result.fields
    assert result.item.identifier == "node_graph.int"


def test_mixed_annotation_and_dataclass():
    @dataclass
    class RowDC:
        sum: int
        product: int

    spec = ss.namespace(x=int, y=RowDC)
    assert spec.fields["y"].is_namespace()
    assert set(spec.fields["y"].fields.keys()) == {"sum", "product"}

    spec = ss.dynamic(RowDC, fixed1=str)
    assert spec.fields["fixed1"].identifier == "node_graph.string"
    assert spec.item.is_namespace()
    assert spec.dynamic is True
    assert set(spec.item.fields.keys()) == {"sum", "product"}


def test_leaf_dataclass_model():
    @dataclass
    class MyLeafDC:
        model_config = {"leaf": True}
        x: int
        y: int

    spec = ss.from_model(MyLeafDC)
    assert not spec.is_namespace()

    @dataclass
    class OtherDC:
        a: int
        b: int

    spec = ss.from_model(ss.Leaf[OtherDC])
    assert not spec.is_namespace()
