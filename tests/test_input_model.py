"""A Pydantic model as a task's wire contract.

``input_model=`` makes a model declare a task's input sockets and hold the
inputs to its rules at three moments: the call that wires the task, the
expansion of a ``@task.graph``, and the run edge of a leaf task. Each test
below is one claim about that contract.
"""

from __future__ import annotations

import enum
from decimal import Decimal
from typing import Annotated, Any, Optional, Union

import pytest
from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    PlainSerializer,
    ValidationError,
    field_validator,
    model_validator,
)
from typing_extensions import TypedDict

from node_graph import Graph, task
from node_graph.engine.local import LocalEngine
from node_graph.input_model import (
    BODY_RECEIVES,
    ModelContractError,
    ModelDerivedValueError,
    TaskInputValidationError,
    TaskOutputValidationError,
    dump_model_field,
    spec_from_model,
    validate_wiring_inputs,
)
from node_graph.socket_spec import namespace as ns


class Color(enum.Enum):
    RED = "red"
    BLUE = "blue"


def links_of(graph: Graph) -> list[str]:
    """Return every link of ``graph`` as ``source -> target``, sorted."""
    return sorted(
        f"{link.from_socket._full_name_with_task} -> {link.to_socket._full_name_with_task}"
        for link in graph.links
    )


@pytest.fixture
def without_wiring_checks(monkeypatch):
    """Run the body with checkpoint A disabled, as a negative control.

    Both of its seams are stubbed: the call, and the write into the task's
    sockets that every route to an input goes through.
    """
    from node_graph import input_model
    from node_graph.task_spec import BaseHandle

    monkeypatch.setattr(
        BaseHandle, "_validate_call_inputs", lambda self, exec_obj, inputs: None
    )
    monkeypatch.setattr(input_model, "validate_task_inputs", lambda task, inputs: None)


# --------------------------------------------------------------------------
# 1. The model is the socket contract
# --------------------------------------------------------------------------


class AddInputs(BaseModel):
    """Two summands, the second optional."""

    x: int
    y: int = 7


@task(input_model=AddInputs)
def add(x, y):
    return x + y


def test_the_sockets_and_their_defaults_come_from_the_model():
    """The bare signature contributes nothing: types, defaults and requiredness are the model's."""
    fields = add._spec.inputs.fields
    assert fields["x"].identifier == "node_graph.int"
    assert fields["x"].meta.required is True
    assert fields["y"].identifier == "node_graph.int"
    assert fields["y"].meta.required is False
    assert fields["y"].default == 7


def test_an_omitted_input_runs_on_the_models_default():
    assert add.run(x=2) == 9


class NudgeInputs(BaseModel):
    """``by`` defaults to ``None``, which reads as a missing input unless the model is asked."""

    x: int
    by: Optional[int] = None


@task(input_model=NudgeInputs)
def nudge(x, by):
    return x if by is None else x + by


def test_a_field_defaulting_to_none_is_not_a_missing_required_input():
    """``from_model`` leaves every field required; the model says which ones are."""
    assert nudge._spec.inputs.fields["by"].meta.required is False


def test_only_a_typed_mapping_is_dynamic():
    """A bare ``dict`` and a ``list`` name no members, so they stay leaf sockets."""

    class Shapes(BaseModel):
        bare: dict = {}
        ordered: list[int] = []
        anything: dict[str, Any] = {}

    fields = spec_from_model(Shapes).fields
    assert fields["bare"].identifier == "node_graph.any"
    assert fields["ordered"].identifier == "node_graph.any"
    assert fields["ordered"].meta.dynamic is False
    assert fields["anything"].meta.dynamic is True


def test_a_typed_mapping_field_names_its_members_type():
    """The keys are unknown at definition time; every member's sockets are not."""

    class Block(BaseModel):
        width: int
        label: str

    class Blocks(BaseModel):
        blocks: dict[str, Block]

    blocks = spec_from_model(Blocks).fields["blocks"]
    assert blocks.meta.dynamic is True
    assert set(blocks.item.fields) == {"width", "label"}
    assert blocks.item.fields["width"].identifier == "node_graph.int"


def test_an_open_topped_model_is_refused():
    class OpenTopped(BaseModel):
        model_config = ConfigDict(extra="allow")
        x: int

    with pytest.raises(ModelContractError, match="declares no contract"):
        spec_from_model(OpenTopped)


def test_a_nested_open_topped_model_is_refused_too():
    """A field the nested model admits has no socket, so it never reaches storage."""

    class OpenInner(BaseModel):
        model_config = ConfigDict(extra="allow")
        x: int

    class HoldsIt(BaseModel):
        inner: OpenInner

    with pytest.raises(ModelContractError, match="OpenInner sets extra='allow'"):
        spec_from_model(HoldsIt)


def test_an_open_topped_model_inside_a_container_is_refused_too():
    """The walk follows containers, so hiding the model in a list changes nothing."""

    class OpenInner(BaseModel):
        model_config = ConfigDict(extra="allow")
        x: int

    class HoldsThem(BaseModel):
        rows: list[OpenInner]

    with pytest.raises(ModelContractError, match="OpenInner sets extra='allow'"):
        spec_from_model(HoldsThem)


def test_a_mapping_keyed_by_anything_but_str_is_refused():
    class IntKeyed(BaseModel):
        counts: dict[int, str]

    with pytest.raises(ModelContractError, match="keys must be str"):
        spec_from_model(IntKeyed)


def test_no_class_path_is_imported_to_rebuild_a_value():
    """A moved class cannot break stored data: nothing reads a path out of the spec to load it.

    The class's name is still recorded, under ``py_type``, and is only ever
    compared as a string -- by link type-checking and in error messages. The
    ``structured_type`` descriptor, which names a class to import, is the one
    a model contract has no use for: the model rebuilds the value instead.
    """

    class PaintInputs(BaseModel):
        color: Color

    @task(input_model=PaintInputs)
    def paint(color):
        return color

    extras = paint._spec.inputs.fields["color"].meta.extras
    assert "structured_type" not in extras
    assert extras["py_type"].endswith("Color")


# --------------------------------------------------------------------------
# 2. Model and signature must agree, loudly, at decoration time
# --------------------------------------------------------------------------


def test_a_signature_default_is_refused():
    with pytest.raises(ModelContractError, match="defaults live in the model"):

        @task(input_model=AddInputs)
        def bad(x, y=7):
            return x + y


def test_a_field_no_parameter_names_is_refused():
    with pytest.raises(
        ModelContractError, match="declares 'y', which 'bad' does not take"
    ):

        @task(input_model=AddInputs)
        def bad(x):
            return x


def test_a_parameter_no_field_declares_is_refused():
    with pytest.raises(
        ModelContractError, match="takes 'z', which AddInputs does not declare"
    ):

        @task(input_model=AddInputs)
        def bad(x, y, z):
            return x


def test_an_annotation_that_contradicts_the_field_is_refused():
    with pytest.raises(ModelContractError, match="but AddInputs declares"):

        @task(input_model=AddInputs)
        def bad(x: str, y):
            return x


def test_var_kwargs_are_refused():
    with pytest.raises(ModelContractError, match="which no model field can name"):

        @task(input_model=AddInputs)
        def bad(x, y, **rest):
            return x


def test_declaring_the_inputs_twice_is_refused():
    with pytest.raises(ModelContractError, match="keep input_model and drop inputs"):

        @task(input_model=AddInputs, inputs=spec_from_model(AddInputs))
        def bad(x, y):
            return x


def test_an_output_model_on_a_graph_is_refused():
    with pytest.raises(ModelContractError, match="not supported on @task.graph"):

        class Out(BaseModel):
            result: int

        @task.graph(input_model=AddInputs, output_model=Out)  # type: ignore[call-arg]
        def bad(x, y):
            return add(x=x, y=y)


# --------------------------------------------------------------------------
# 3. Checkpoint A -- what is written at the call
# --------------------------------------------------------------------------


class PriceInputs(BaseModel):
    """A ``Decimal`` and a fixed-length tuple: two shapes a socket reads as ``any``."""

    amount: Decimal
    pair: tuple[int, int]
    ratio: float = Field(gt=0)


@task(input_model=PriceInputs)
def price(amount, pair, ratio):
    return amount


GOOD_PRICE = {"amount": Decimal("1.5"), "pair": (1, 2), "ratio": 0.5}


@pytest.mark.parametrize(
    "field, value",
    [
        ("amount", "not a number"),
        ("pair", [1, 2, 3]),
        ("ratio", -1.0),
    ],
    ids=[
        "decimal-from-nonsense",
        "tuple-of-the-wrong-length",
        "constraint-the-socket-cannot-see",
    ],
)
def test_a_bad_literal_fails_at_the_line_that_wrote_it(field, value):
    """A field whose socket identifier is ``any`` has no other build-time check."""
    payload = dict(GOOD_PRICE, **{field: value})

    @task.graph()
    def wires_a_bad_value():
        return price(**payload)

    with pytest.raises(TaskInputValidationError) as excinfo:
        wires_a_bad_value.build()
    assert "Task 'price'" in str(excinfo.value)
    assert field in str(excinfo.value)


@pytest.mark.parametrize(
    "field, value",
    [
        ("amount", "not a number"),
        ("pair", [1, 2, 3]),
        ("ratio", -1.0),
    ],
    ids=[
        "decimal-from-nonsense",
        "tuple-of-the-wrong-length",
        "constraint-the-socket-cannot-see",
    ],
)
def test_a_bad_literal_at_the_call_passes_without_checkpoint_a(
    without_wiring_checks, field, value
):
    """The negative control: the socket layer types these as ``any`` and lets them through."""
    payload = dict(GOOD_PRICE, **{field: value})

    @task.graph()
    def wires_a_bad_value():
        return price(**payload)

    assert wires_a_bad_value.build() is not None


def test_a_literal_the_socket_layer_also_refuses_gets_the_models_message():
    """Where both can see the value, the model's error is the one that arrives."""

    @task.graph()
    def wires_a_string(m):
        return add(x="sixty", y=m)

    with pytest.raises(TaskInputValidationError) as excinfo:
        wires_a_string.build(m=1)
    assert "Task 'add'" in str(excinfo.value)
    assert "\nx\n" in str(excinfo.value)


class BoxInputs(BaseModel):
    cfg: dict[str, int]
    n: int


@task(input_model=BoxInputs)
def box(cfg, n):
    return n


def test_a_bad_literal_inside_a_container_names_its_path():
    @task.graph()
    def wires_a_bad_member(m):
        return box(cfg={"x": "nope"}, n=m)

    with pytest.raises(TaskInputValidationError, match=r"cfg\.x"):
        wires_a_bad_member.build(m=1)


def test_a_reference_inside_a_container_is_not_a_bad_value():
    """A link written into one member of a mapping is what a graph is for."""

    @task.graph()
    def wires_a_reference(m):
        return box(cfg={"x": m}, n=m)

    assert len(wires_a_reference.build(m=1).links) == 3


@task()
def untyped(a, b):
    return a


def test_wiring_a_reference_leaves_every_link_where_it_was(monkeypatch):
    """Checkpoint A validates and discards, so the graph it builds is the graph without it.

    Pydantic strips the proxy a tagged value wears for nearly every field
    type, so a validated copy would turn a link into a literal. This compares
    the same graph built with the check and without it.
    """

    @task.graph()
    def chain(m, n):
        first = untyped(a=m, b=n)
        return add(x=m, y=first.result)

    from node_graph.task_spec import BaseHandle

    with monkeypatch.context() as patched:
        patched.setattr(
            BaseHandle, "_validate_call_inputs", lambda self, exec_obj, inputs: None
        )
        without = links_of(chain.build(m=1, n=2))
    assert links_of(chain.build(m=1, n=2)) == without
    assert any("graph_inputs.inputs.m -> add.inputs.x" == link for link in without)


def test_validating_at_the_call_hands_back_the_very_objects_it_was_given():
    """The values are passed on by identity, which is what keeps a reference a reference."""

    class Sentinel:
        pass

    given = {"cfg": {"x": 1}, "n": 2}
    before = {"cfg": id(given["cfg"]), "n": id(given["n"])}
    validate_wiring_inputs(BoxInputs, given, label="box")
    assert {name: id(value) for name, value in given.items()} == before


def test_a_field_validator_does_not_fire_at_the_call():
    """The boundary, pinned: checkpoint A checks types, and only types.

    The model runs as a flat shadow with the user's decorators left out, so a
    rule written for whole, resolved inputs is not judged against a
    placeholder. The rule still fires at the run edge.
    """

    class Capped(BaseModel):
        a: int
        b: int

        @field_validator("a")
        @classmethod
        def cap(cls, value):
            if value > 100:
                raise ValueError("a must be at most 100")
            return value

    @task(input_model=Capped)
    def capped(a, b):
        return a + b

    @task.graph()
    def over_the_cap(m):
        return capped(a=1000, b=m)

    assert over_the_cap.build(m=1) is not None
    with pytest.raises(TaskInputValidationError, match="at most 100"):
        capped.run(a=1000, b=1)


def test_a_before_validator_is_not_honoured_at_the_call():
    """A normalizer is not a type, so the call sees only what the annotation admits."""

    class Narrow(BaseModel):
        kpoints: list[list[int]]

        @field_validator("kpoints", mode="before")
        @classmethod
        def as_rows(cls, value):
            if value and not isinstance(value[0], list):
                return [value]
            return value

    @task(input_model=Narrow)
    def narrow(kpoints):
        return kpoints

    @task.graph()
    def flat(m):
        return narrow(kpoints=[1, 2, 3])

    with pytest.raises(TaskInputValidationError, match="kpoints"):
        flat.build(m=1)


def test_a_widened_annotation_admits_what_the_normalizer_would_accept():
    """The fix for the case above: say in the type what the field takes."""

    class Widened(BaseModel):
        kpoints: list[int] | list[list[int]]

    @task(input_model=Widened)
    def widened(kpoints):
        return kpoints

    @task.graph()
    def flat(m):
        return widened(kpoints=[1, 2, 3])

    assert flat.build(m=1) is not None


# --------------------------------------------------------------------------
# 4. Checkpoint B -- a graph's resolved inputs
# --------------------------------------------------------------------------


class SpanInputs(BaseModel):
    """Two ints the socket layer accepts; their order is the model's rule."""

    low: int
    high: int = Field(le=100)

    @model_validator(mode="after")
    def ordered(self):
        if self.low >= self.high:
            raise ValueError("low must be below high")
        return self


@task.graph(input_model=SpanInputs)
def span(low, high):
    return add(x=low, y=high)


#: What the graph body below saw, read back after the build.
SEEN: dict[str, str] = {}


@task.graph(input_model=SpanInputs)
def watched(low, high):
    SEEN["low"] = type(low).__name__
    return add(x=low, y=high)


def test_a_graph_expands_when_its_inputs_satisfy_the_model():
    assert len(span.build(low=1, high=3).links) == 3


def test_a_cross_field_rule_fires_when_the_graph_is_built():
    with pytest.raises(TaskInputValidationError) as excinfo:
        span.build(low=9, high=3)
    assert "Graph 'span'" in str(excinfo.value)
    assert "low must be below high" in str(excinfo.value)


def test_a_field_constraint_the_socket_cannot_express_fires_at_the_same_place():
    with pytest.raises(TaskInputValidationError, match="less than or equal to 100"):
        span.build(low=1, high=500)


def test_a_cross_field_rule_passes_without_checkpoint_b(monkeypatch):
    """The negative control: no other layer knows the two fields are related."""
    import node_graph.utils.graph as graph_utils

    monkeypatch.setattr(
        graph_utils,
        "_validate_graph_body_inputs",
        lambda func, inputs, name, adapter=None: None,
    )
    assert span.build(low=9, high=3) is not None


def test_a_value_of_the_wrong_type_never_reaches_the_body():
    """Where the socket layer's own check does not reach, the model's does."""

    class Recipe(BaseModel):
        amount: Decimal

    @task.graph(input_model=Recipe)
    def recipe(amount):
        return add(x=1, y=2)

    with pytest.raises(TaskInputValidationError, match="amount"):
        recipe.build(amount="not a number")


def test_the_body_still_receives_the_tagged_values_it_needs():
    """Validation builds fresh objects; the body is handed the originals, so links survive."""
    SEEN.clear()
    graph = watched.build(low=1, high=3)
    assert SEEN["low"] == "TaggedValue"
    assert "graph_inputs.inputs.low -> add.inputs.x" in links_of(graph)


class Doubling(BaseModel):
    """``total`` is twice ``count`` -- a rule, stated as a rule."""

    count: int
    total: int

    @model_validator(mode="after")
    def check_total(self):
        if self.total != self.count * 2:
            raise ValueError("total must be twice count")
        return self


@task.graph(input_model=Doubling)
def doubling(count, total):
    return add(x=count, y=total)


def test_a_nested_graph_checks_the_value_the_run_produced():
    """A subgraph's inputs are literals only from its own point of view."""

    @task()
    def wrong_total(count):
        return count * 3

    @task.graph()
    def outer(count):
        computed = wrong_total(count=count)
        return doubling(count=count, total=computed.result)

    graph = Graph(name="nested", outputs=ns(result=Any))
    node = graph.add_task(outer, "outer", count=2)
    graph.add_link(node.outputs.result, graph.outputs.result)

    with pytest.raises(TaskInputValidationError, match="total must be twice count"):
        LocalEngine().run(graph)


# --------------------------------------------------------------------------
# 5. Validation may change how a value is spelled, not what it says
# --------------------------------------------------------------------------


class Derived(BaseModel):
    """A model that fills ``total`` in rather than checking it."""

    count: int
    total: int

    @model_validator(mode="after")
    def derive_total(self):
        object.__setattr__(self, "total", self.count * 2)
        return self


@task.graph(input_model=Derived)
def derived(count, total):
    return add(x=count, y=total)


def test_a_derivation_that_leaves_a_resolved_value_alone_is_accepted():
    assert derived.build(count=2, total=4) is not None


def test_a_derivation_that_rewrites_its_input_is_refused():
    with pytest.raises(ModelDerivedValueError) as excinfo:
        derived.build(count=2, total=7)
    assert "'derived'" in str(excinfo.value)
    assert "'total'" in str(excinfo.value)
    assert "changed it from 7 to 4" in str(excinfo.value)


class Coercions(BaseModel):
    """Three fields whose stored spelling differs from the object the body wants."""

    amount: Decimal
    color: Color
    pair: tuple[int, int]


@task.graph(input_model=Coercions)
def coercions(amount, color, pair):
    return add(x=1, y=2)


def test_pure_coercion_is_not_a_change_of_content():
    assert coercions.build(amount="60", color="red", pair=[1, 2]) is not None


def test_a_default_filling_an_omitted_field_is_not_a_change():
    class WithDefault(BaseModel):
        x: int
        y: int = 7

    @task.graph(input_model=WithDefault)
    def with_default(x, y):
        return add(x=x, y=y)

    assert with_default.build(x=1) is not None


def test_a_rewriting_validator_is_refused_at_the_run_edge_too():
    class Shouting(BaseModel):
        name: str

        @field_validator("name")
        @classmethod
        def shout(cls, value):
            return value.upper()

    @task(input_model=Shouting)
    def shouting(name):
        return name

    with pytest.raises(ModelDerivedValueError, match="'name'"):
        shouting.run(name="silicon")
    # Already resolved, so the rule changes nothing and the task runs.
    assert shouting.run(name="SILICON") == "SILICON"


# --------------------------------------------------------------------------
# 6. Checkpoint C -- the run edge
# --------------------------------------------------------------------------


class BodyRan(RuntimeError):
    """Raised by a body that should not have been reached."""


@task(input_model=SpanInputs)
def announcing_span(low, high):
    raise BodyRan


@task(inputs=spec_from_model(SpanInputs))
def announcing_span_without_model(low, high):
    raise BodyRan


def test_the_body_receives_what_the_model_declares():
    @task(input_model=Coercions, outputs=["amount", "color", "pair"])
    def kinds(amount, color, pair):
        return {
            "amount": type(amount).__name__,
            "color": color is Color.RED,
            "pair": type(pair).__name__,
        }

    assert kinds.run(amount="60", color="red", pair=[1, 2]) == {
        "amount": "Decimal",
        "color": True,
        "pair": "tuple",
    }


def test_a_stored_value_the_model_refuses_fails_before_the_body_runs():
    """The body announces itself by raising, and what comes back is the model's refusal."""
    with pytest.raises(TaskInputValidationError, match="low must be below high"):
        announcing_span.run(low=9, high=3)


def test_without_the_model_the_same_values_reach_the_body():
    """The control: the same sockets, no contract, and the rule is never consulted."""
    with pytest.raises(BodyRan):
        announcing_span_without_model.run(low=9, high=3)


class SumAndProduct(BaseModel):
    total: int
    product: int


def test_the_output_sockets_come_from_the_output_model():
    @task(output_model=SumAndProduct)
    def combine(x, y):
        return {"total": x + y, "product": x * y}

    assert set(combine._spec.outputs.fields) == {"total", "product"}
    assert combine.run(x=2, y=3) == {"total": 5, "product": 6}


def test_a_missing_output_fails_at_the_task_that_produced_it():
    @task(output_model=SumAndProduct)
    def forgets_product(x, y):
        return {"total": x + y}

    with pytest.raises(TaskOutputValidationError, match="product"):
        forgets_product.run(x=2, y=3)


def test_a_mistyped_output_fails_at_the_task_that_produced_it():
    @task(output_model=SumAndProduct)
    def mistypes_total(x, y):
        return {"total": "not a number", "product": x * y}

    with pytest.raises(TaskOutputValidationError, match="total"):
        mistypes_total.run(x=2, y=3)


# --------------------------------------------------------------------------
# 7. What a task without a model does
# --------------------------------------------------------------------------


@task()
def plain_add(x: int, y: int = 7) -> int:
    return x + y


def test_a_task_without_a_model_is_untouched():
    fields = plain_add._spec.inputs.fields
    assert fields["x"].identifier == "node_graph.int"
    assert fields["y"].default == 7
    assert plain_add.run(x=2) == 9


def test_a_model_that_is_not_a_model_is_refused():
    with pytest.raises(ModelContractError, match="must be a pydantic BaseModel"):

        @task(input_model=dict)  # type: ignore[arg-type]
        def bad(x):
            return x


def test_the_model_still_validates_when_called_directly():
    """The contract lives on the model, so it holds outside a graph too."""
    with pytest.raises(ValidationError):
        SpanInputs(low=9, high=3)


# --------------------------------------------------------------------------
# 8. A value the model has no JSON form for
# --------------------------------------------------------------------------


class Opaque:
    """An object with no JSON form at all."""


class HoldsAnOpaqueValue(BaseModel):
    payload: Any
    n: int


@task(input_model=HoldsAnOpaqueValue)
def holds_an_opaque_value(payload, n):
    return n


def test_a_value_with_no_json_form_does_not_break_the_check():
    """It is compared as the object it is, rather than aborting on a serializer error."""
    assert holds_an_opaque_value.run(payload=Opaque(), n=1) == 1


class ReplacesAnOpaqueValue(BaseModel):
    payload: Any
    n: int

    @model_validator(mode="after")
    def _replace(self):
        self.payload = Opaque()
        return self


@task(input_model=ReplacesAnOpaqueValue)
def replaces_an_opaque_value(payload, n):
    return n


def test_replacing_a_value_with_no_json_form_is_still_refused():
    with pytest.raises(ModelDerivedValueError, match="'payload'"):
        replaces_an_opaque_value.run(payload=Opaque(), n=1)


def test_a_value_with_no_json_form_is_stored_as_it_stands():
    payload = Opaque()
    assert dump_model_field(HoldsAnOpaqueValue, "payload", payload) is payload


# --------------------------------------------------------------------------
# 9. What a body receives for each kind of field
# --------------------------------------------------------------------------


class Marker:
    """A class pydantic can only accept instances of."""


class EveryKind(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    text: str
    number: int
    fraction: float
    flag: bool
    mapping: dict
    items: list
    anything: Any
    amount: Decimal
    marker: Marker
    nested: dict[str, int]


@task(input_model=EveryKind)
def every_kind(
    text, number, fraction, flag, mapping, items, anything, amount, marker, nested
):
    return text


def _arrival(name):
    return every_kind._spec.inputs.fields[name].meta.extras[BODY_RECEIVES]


@pytest.mark.parametrize(
    "field",
    ["text", "number", "fraction", "flag", "mapping", "items", "amount"],
)
def test_a_field_pydantic_can_rebuild_is_read_as_python(field):
    """The engine's wrapper comes off, because the model builds the value back."""
    assert _arrival(field) == "python"


@pytest.mark.parametrize("field", ["anything", "marker"])
def test_a_field_only_an_instance_satisfies_is_read_as_a_node(field):
    """``Any`` declares nothing to rebuild, and an arbitrary class wants its own instance."""
    assert _arrival(field) == "node"


def test_the_member_of_a_typed_mapping_carries_the_mark_too():
    item = every_kind._spec.inputs.fields["nested"].item
    assert item.meta.extras[BODY_RECEIVES] == "python"


def test_a_nested_models_leaves_carry_the_mark_and_the_namespace_does_not():
    class Inner(BaseModel):
        x: int

    class Outer(BaseModel):
        inner: Inner

    @task(input_model=Outer)
    def outer(inner):
        return inner

    namespace = outer._spec.inputs.fields["inner"]
    assert BODY_RECEIVES not in namespace.meta.extras
    assert namespace.fields["x"].meta.extras[BODY_RECEIVES] == "python"


def _kind_of(annotation):
    """Return the mark a one-field model gives ``annotation``."""

    class OneField(BaseModel):
        model_config = ConfigDict(arbitrary_types_allowed=True)

        field: annotation

    @task(input_model=OneField)
    def one_field(field):
        return field

    return one_field._spec.inputs.fields["field"].meta.extras[BODY_RECEIVES]


@pytest.mark.parametrize(
    "annotation, expected",
    [
        (Optional[int], "python"),
        (Optional[Marker], "node"),
        (Union[int, str], "python"),
        (Union[Marker, Opaque], "node"),
    ],
    ids=["optional-python", "optional-node", "two-python-arms", "two-node-arms"],
)
def test_a_union_whose_arms_agree_takes_their_answer(annotation, expected):
    """``None`` is neither kind, so ``X | None`` is read as ``X``."""
    assert _kind_of(annotation) == expected


def test_a_union_spanning_both_kinds_is_refused_at_decoration():
    """A socket delivers one form, so nothing here could choose between them."""
    with pytest.raises(ModelContractError) as excinfo:
        _kind_of(Union[int, Marker])
    message = str(excinfo.value)
    assert "OneField.field" in message
    assert "int" in message and "Marker" in message


def test_a_none_arm_does_not_make_a_mixed_union_agree():
    """The control: dropping ``None`` leaves the two disagreeing arms it was hiding."""
    with pytest.raises(ModelContractError, match="OneField.field"):
        _kind_of(Optional[Union[int, Marker]])


# --------------------------------------------------------------------------
# 10. The model's own config decides what its fields accept
# --------------------------------------------------------------------------


class Stripped(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    text: str


@task(input_model=Stripped)
def stripped(text):
    return text


def test_a_config_that_coerces_is_not_a_derivation():
    """Both sides strip, because both carry the config, so the content is unchanged."""
    assert stripped.run(text="  silicon  ") == "silicon"


class StripsByHand(BaseModel):
    text: str

    @field_validator("text")
    @classmethod
    def _strip(cls, value):
        return value.strip()


@task(input_model=StripsByHand)
def strips_by_hand(text):
    return text


def test_the_control_a_validator_doing_the_same_thing_is_a_derivation():
    """A rule is the model's own; only one side runs it, so the content changes."""
    with pytest.raises(ModelDerivedValueError, match="'text'"):
        strips_by_hand.run(text="  silicon  ")


class Aliased(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    amount: int = Field(alias="qty")


@task(input_model=Aliased)
def aliased(amount):
    return amount


def test_a_field_reachable_by_its_own_name_is_accepted_at_the_call():
    assert aliased.run(amount=5) == 5


def test_an_arbitrary_type_is_accepted_where_its_config_allows_it():
    marker = Marker()
    assert (
        every_kind.run(
            text="a",
            number=1,
            fraction=1.0,
            flag=True,
            mapping={},
            items=[],
            anything="whatever",
            amount=Decimal("1"),
            marker=marker,
            nested={"k": 1},
        )
        == "a"
    )


# --------------------------------------------------------------------------
# 11. A field kept out of the model's dump
# --------------------------------------------------------------------------


class Excluded(BaseModel):
    secret: str = Field(exclude=True)
    n: int

    @field_validator("secret")
    @classmethod
    def _rewrite(cls, value):
        return value + "-REWRITTEN"


@task(input_model=Excluded)
def excluded(secret, n):
    return secret


def test_a_field_kept_out_of_a_dump_is_still_compared():
    """``exclude=True`` says what is rendered, not what may be rewritten unseen."""
    with pytest.raises(ModelDerivedValueError, match="'secret'"):
        excluded.run(secret="abc", n=1)


class HiddenByItsAnnotation(BaseModel):
    """Every value renders as ``0``, so a rewrite leaves no trace in the dump."""

    amount: Annotated[int, PlainSerializer(lambda value: 0, return_type=int)]

    @field_validator("amount")
    @classmethod
    def _double(cls, value):
        return value * 2


@task(input_model=HiddenByItsAnnotation)
def hidden_by_its_annotation(amount):
    return amount


def test_a_serializer_written_into_the_annotation_cannot_hide_a_rewrite():
    """It renders, so the twin drops it and compares what the field actually says."""
    with pytest.raises(ModelDerivedValueError, match="changed it from 1 to 2"):
        hidden_by_its_annotation.run(amount=1)


def test_the_same_serializer_still_decides_the_stored_form():
    """The control: dropping it from the twin does not drop it from storage."""
    assert dump_model_field(HiddenByItsAnnotation, "amount", 7) == 0


def test_an_excluded_fields_default_is_stored_as_it_stands():
    """``dump_model_field`` has no rendered form to give, and says the value instead."""

    class WithExcludedDefault(BaseModel):
        secret: str = Field(default="abc", exclude=True)

    assert dump_model_field(WithExcludedDefault, "secret", "abc") == "abc"


# --------------------------------------------------------------------------
# 12. The reference the invariance check compares against
# --------------------------------------------------------------------------


class MutatesInPlace(BaseModel):
    rows: Any
    n: int

    @model_validator(mode="after")
    def _append(self):
        self.rows.append("INJECTED")
        return self


@task(input_model=MutatesInPlace)
def mutates_in_place(rows, n):
    return list(rows)


def test_a_validator_that_rewrites_its_input_in_place_is_refused():
    """The reference is read before the model runs, so there is still one to compare with."""
    with pytest.raises(ModelDerivedValueError, match="'rows'"):
        mutates_in_place.run(rows=["a"], n=1)


class Rebinds(BaseModel):
    rows: list
    n: int

    @model_validator(mode="after")
    def _rebind(self):
        self.rows = [*self.rows, "INJECTED"]
        return self


@task(input_model=Rebinds)
def rebinds(rows, n):
    return list(rows)


def test_a_validator_that_replaces_its_input_is_refused():
    with pytest.raises(ModelDerivedValueError, match="'rows'"):
        rebinds.run(rows=["a"], n=1)


class Leaf(BaseModel):
    x: int


class ReachesInside(BaseModel):
    model_config = ConfigDict(revalidate_instances="never")

    leaf: Leaf
    n: int

    @model_validator(mode="after")
    def _reach(self):
        self.leaf.x = 999
        return self


@task(input_model=ReachesInside)
def reaches_inside(leaf, n):
    return leaf.x


def test_a_validator_that_reaches_into_a_nested_instance_is_refused():
    """The caller's own instance is mutated, so only a reference taken first sees it."""
    with pytest.raises(ModelDerivedValueError, match="'leaf'"):
        reaches_inside.run(leaf=Leaf(x=1), n=1)


def test_without_taking_the_reference_first_the_mutation_is_invisible():
    """The control: read the reference after the model ran and both sides say the same."""
    from node_graph import input_model as module

    given = {"rows": ["a"], "n": 1}
    validated = MutatesInPlace.model_validate(dict(given))
    after_the_fact = module.content_snapshot(MutatesInPlace, given)
    module.check_content_invariance(
        MutatesInPlace, after_the_fact, validated, label="control"
    )
    assert given["rows"] == ["a", "INJECTED"]


# --------------------------------------------------------------------------
# 13. An annotation's own validators run on both sides
# --------------------------------------------------------------------------


class AnnotatedIdempotent(BaseModel):
    amount: Annotated[int, AfterValidator(lambda value: abs(value))]


@task(input_model=AnnotatedIdempotent)
def annotated_idempotent(amount):
    return amount


def test_an_idempotent_annotation_validator_passes():
    """It runs on both sides and lands on the same value, so nothing changed."""
    assert annotated_idempotent.run(amount=-6) == 6


class AnnotatedDoubling(BaseModel):
    amount: Annotated[int, AfterValidator(lambda value: value * 2)]


@task(input_model=AnnotatedDoubling)
def annotated_doubling(amount):
    return amount


def test_a_non_idempotent_annotation_validator_is_refused():
    """Running twice doubles twice, so the two sides disagree and the write is refused."""
    with pytest.raises(ModelDerivedValueError, match="changed it from 6 to 12"):
        annotated_doubling.run(amount=3)


# --------------------------------------------------------------------------
# 14. A nested field accepts the class it names
# --------------------------------------------------------------------------


class Point(BaseModel):
    x: int


class HoldsAPoint(BaseModel):
    point: Point


class HoldsPointList(BaseModel):
    points: list[Point]


class HoldsPointMapping(BaseModel):
    points: dict[str, Point]


@task(input_model=HoldsAPoint)
def holds_a_point(point):
    return point


@task(input_model=HoldsPointList)
def holds_point_list(points):
    return points


@task(input_model=HoldsPointMapping)
def holds_point_mapping(points):
    return points


@pytest.mark.parametrize(
    "handle, written",
    [
        (holds_a_point, {"point": Point(x=1)}),
        (holds_point_list, {"points": [Point(x=1)]}),
        (holds_point_mapping, {"points": {"k": Point(x=1)}}),
    ],
    ids=["plain", "in-a-list", "in-a-mapping"],
)
def test_the_class_a_field_names_is_accepted_where_it_is_written(handle, written):
    """A shadow is a different class; the class the field names is not a wrong value."""
    with Graph(name="instances"):
        assert handle(**written) is not None


@pytest.mark.parametrize(
    "handle, written",
    [
        (holds_a_point, {"point": {"x": "nope"}}),
        (holds_point_list, {"points": [{"x": "nope"}]}),
        (holds_point_mapping, {"points": {"k": {"x": "nope"}}}),
    ],
    ids=["plain", "in-a-list", "in-a-mapping"],
)
def test_a_wrong_value_in_the_same_place_is_still_refused(handle, written):
    """The control: accepting the class does not stop the shadow checking a dict."""
    with Graph(name="instances_bad"):
        with pytest.raises(TaskInputValidationError, match="x"):
            handle(**written)


# --------------------------------------------------------------------------
# 15. Checkpoint A fires wherever an input is written
# --------------------------------------------------------------------------


class Bounded(BaseModel):
    amount: int = Field(gt=0)
    other: int = 5


@task(input_model=Bounded)
def bounded(amount, other):
    return amount


def test_a_bad_value_is_refused_when_the_task_is_called():
    with pytest.raises(TaskInputValidationError, match="amount"):
        with Graph(name="call"):
            bounded(amount="bad", other=1)


def test_a_bad_value_is_refused_when_it_is_passed_to_add_task():
    graph = Graph(name="added")
    with pytest.raises(TaskInputValidationError, match="amount"):
        graph.add_task(bounded, "b", amount="bad")


def test_a_bad_value_is_refused_when_it_is_set_on_the_task():
    graph = Graph(name="set")
    node = graph.add_task(bounded, "b")
    with pytest.raises(TaskInputValidationError, match="amount"):
        node.set_inputs({"amount": "bad"})


def test_a_constraint_the_socket_cannot_see_is_refused_at_add_task():
    graph = Graph(name="constrained")
    with pytest.raises(TaskInputValidationError, match="greater than 0"):
        graph.add_task(bounded, "b", amount=-1)


def test_without_the_check_add_task_accepts_the_constraint_breach(monkeypatch):
    """The control: the socket layer types ``amount`` as ``int`` and cannot see ``gt=0``."""
    from node_graph import input_model as module

    monkeypatch.setattr(module, "validate_task_inputs", lambda task, inputs: None)
    graph = Graph(name="unchecked")
    assert graph.add_task(bounded, "b", amount=-1) is not None


def test_writing_only_some_of_the_fields_is_not_a_missing_input():
    """Inputs may be written a few at a time, and a link may supply the rest."""
    graph = Graph(name="partial")
    assert graph.add_task(bounded, "b") is not None
    assert graph.add_task(bounded, "c", amount=1) is not None


def test_a_task_written_into_an_input_is_a_reference_not_a_value():
    graph = Graph(name="linked")
    producer = graph.add_task(bounded, "p", amount=1)
    assert graph.add_task(bounded, "c", amount=producer.outputs.result) is not None


# --------------------------------------------------------------------------
# 16. A value whose inequality is not a yes or no
# --------------------------------------------------------------------------


class HoldsAnArray(BaseModel):
    payload: Any
    n: int


@task(input_model=HoldsAnArray)
def holds_an_array(payload, n):
    return n


class ReplacesTheArray(BaseModel):
    payload: Any
    n: int

    @model_validator(mode="after")
    def _replace(self):
        import numpy

        self.payload = numpy.array([9, 9])
        return self


@task(input_model=ReplacesTheArray)
def replaces_the_array(payload, n):
    return n


@pytest.mark.parametrize("size", [1, 2], ids=["one-element", "two-elements"])
def test_an_array_the_model_leaves_alone_passes(size):
    """``array != array`` answers with an array, which the check must not read as a bool."""
    numpy = pytest.importorskip("numpy")
    assert holds_an_array.run(payload=numpy.arange(size), n=1) == 1


@pytest.mark.parametrize("size", [1, 2], ids=["one-element", "two-elements"])
def test_replacing_an_array_is_still_refused(size):
    """The control: the comparison still decides, it just cannot ask ``if``."""
    numpy = pytest.importorskip("numpy")
    with pytest.raises(ModelDerivedValueError, match="'payload'"):
        replaces_the_array.run(payload=numpy.arange(size), n=1)


# --------------------------------------------------------------------------
# 17. A container of values only an instance satisfies
# --------------------------------------------------------------------------


def _spec_of(annotation):
    """Return the spec a one-field model gives ``annotation``."""

    class OneField(BaseModel):
        model_config = ConfigDict(arbitrary_types_allowed=True)

        field: annotation

    return spec_from_model(OneField).fields["field"]


class MarkerRow(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    marker: Marker


class MixedRow(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    marker: Marker
    count: int


class MarkerEntry(TypedDict):
    marker: Marker


class MixedEntry(TypedDict):
    marker: Marker
    count: int


def test_a_list_of_values_only_an_instance_satisfies_is_refused():
    """Storage keeps a list as one node of plain data, so the members cannot come back."""
    with pytest.raises(ModelContractError, match="cannot round-trip through storage"):
        _spec_of(list[Marker])


def test_the_refusal_names_the_mapping_that_does_work():
    with pytest.raises(ModelContractError, match=r"dict\[str, Marker\]"):
        _spec_of(list[Marker])


def test_a_mapping_of_the_same_type_is_the_shape_that_survives():
    """The control: one socket, and one node, per key."""
    spec = _spec_of(dict[str, Marker])
    assert spec.meta.dynamic is True
    assert spec.item.meta.extras[BODY_RECEIVES] == "node"


def test_a_list_of_plain_data_is_untouched():
    """The refusal is about what the members are, not about the list."""
    assert _spec_of(list[int]).meta.extras[BODY_RECEIVES] == "python"


def test_a_list_of_anything_is_untouched():
    """``Any`` declares nothing, so it declares nothing to refuse either."""
    assert _spec_of(list[Any]).meta.extras[BODY_RECEIVES] == "python"


def test_a_typed_dict_of_engine_types_arrives_as_the_engine_stored_it():
    """Pydantic builds the mapping readily; what is inside it still wants an instance."""
    assert _spec_of(MarkerEntry).meta.extras[BODY_RECEIVES] == "node"


def test_a_typed_dict_whose_members_disagree_is_refused():
    with pytest.raises(ModelContractError, match="whose members disagree"):
        _spec_of(MixedEntry)


def test_a_model_in_a_list_is_read_through_its_own_fields():
    """``list[MarkerRow]`` is a list of values only an instance satisfies, once removed."""
    with pytest.raises(ModelContractError, match="cannot round-trip through storage"):
        _spec_of(list[MarkerRow])


def test_a_model_in_a_list_whose_members_disagree_is_refused():
    with pytest.raises(ModelContractError, match="whose members disagree"):
        _spec_of(list[MixedRow])


def test_a_list_of_models_of_plain_data_still_works():
    """The control: the same shape, with members the model can rebuild."""
    assert _spec_of(list[Point]).meta.extras[BODY_RECEIVES] == "python"


def test_a_union_refusal_reads_as_a_sentence():
    """One arm on each side, so the verbs are singular and ``Any`` says what it is."""
    with pytest.raises(ModelContractError) as excinfo:
        _spec_of(Union[int, Marker])
    message = str(excinfo.value)
    assert "int is rebuilt from plain data" in message
    assert "Marker arrives as the engine stored it" in message


def test_an_any_arm_is_named_for_what_it_declares():
    with pytest.raises(ModelContractError, match="Any declares nothing to rebuild"):
        _spec_of(Union[int, Any])


# --------------------------------------------------------------------------
# 18. A field reachable only by its alias
# --------------------------------------------------------------------------


class AliasedOnly(BaseModel):
    """No ``populate_by_name``: as written, the model takes ``qty`` and not ``amount``."""

    amount: int = Field(alias="qty")


@task(input_model=AliasedOnly)
def aliased_only(amount):
    return amount


def test_the_socket_is_named_by_the_field_not_the_alias():
    assert set(aliased_only._spec.inputs.fields) == {"amount"}


def test_an_aliased_field_is_accepted_under_the_name_that_names_its_socket():
    """The socket delivers ``amount``, so every checkpoint has to take it."""
    assert aliased_only.run(amount=5) == 5


def test_an_aliased_field_is_still_accepted_under_its_alias():
    """Widening what is accepted takes nothing away from the model as written."""
    assert AliasedOnly.model_validate({"qty": 5}).amount == 5


def test_a_field_renamed_by_an_alias_generator_is_accepted_too():
    class Generated(BaseModel):
        model_config = ConfigDict(alias_generator=lambda name: name.upper())

        amount: int

    @task(input_model=Generated)
    def generated(amount):
        return amount

    assert generated.run(amount=5) == 5


def test_the_model_as_written_still_refuses_the_field_name():
    """The control: the acceptance is added for the contract, not taken from the user."""
    with pytest.raises(ValidationError):
        AliasedOnly.model_validate({"amount": 5})


# --------------------------------------------------------------------------
# 19. What the body returns
# --------------------------------------------------------------------------


class OpaqueOutput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    payload: Marker
    n: int


def test_an_output_with_no_json_form_is_returned_as_it_stands():
    """One field the model cannot render does not cost the others theirs.

    Dumping the whole model raises on ``Marker``; per field, only that field
    has no rendering and it keeps the object instead. The engine copies the
    object on its way out, so it is compared by type.
    """

    @task(output_model=OpaqueOutput)
    def emits(x):
        return {"payload": Marker(), "n": x}

    returned = emits.run(x=3)
    assert isinstance(returned["payload"], Marker)
    assert returned["n"] == 3


def test_a_returned_key_the_model_does_not_declare_is_refused():
    """It has no socket to be written to, so it would be dropped between here and there."""

    @task(output_model=SumAndProduct)
    def emits_extra(x, y):
        return {"total": x + y, "product": x * y, "difference": x - y}

    with pytest.raises(TaskOutputValidationError, match="'difference'"):
        emits_extra.run(x=3, y=2)


def test_the_declared_keys_alone_still_pass():
    """The control: the same body without the extra key is accepted."""

    @task(output_model=SumAndProduct)
    def emits_declared(x, y):
        return {"total": x + y, "product": x * y}

    assert emits_declared.run(x=3, y=2) == {"total": 5, "product": 6}
