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
    ValidationError,
    field_validator,
    model_validator,
)

from node_graph import Graph, task
from node_graph.engine.local import LocalEngine
from node_graph.input_model import (
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
    """Run the body with checkpoint A disabled, as a negative control."""
    from node_graph.task_spec import BaseHandle

    monkeypatch.setattr(
        BaseHandle, "_validate_call_inputs", lambda self, exec_obj, inputs: None
    )


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
