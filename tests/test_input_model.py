"""A Pydantic model as a task's wire contract.

``input_model=`` makes a model declare a task's input sockets and hold the
inputs to its rules at three moments: the call that wires the task, the
expansion of a ``@task.graph``, and the run edge of a leaf task. Each test
below is one claim about that contract.
"""

from __future__ import annotations

import enum
from decimal import Decimal
from typing import Annotated, Any, Literal, Optional, Union

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


class Spin(enum.Enum):
    """The four spin treatments a workflow accepts."""

    NONE = "none"
    COLLINEAR = "collinear"
    NON_COLLINEAR = "non_collinear"
    SPIN_ORBIT = "spin_orbit"


class PhInputs(BaseModel):
    spin: Spin = Spin.NONE
    structure: str

    @field_validator("spin")
    @classmethod
    def _supported(cls, value):
        if value in (Spin.NON_COLLINEAR, Spin.SPIN_ORBIT):
            raise ValueError(
                "ph.x has no electric-field perturbation for noncollinear magnetism"
            )
        return value


#: What each run of ``ph``'s body was handed, so a test can see it did not run.
ph_ran_with: list = []


@task(input_model=PhInputs)
def ph(spin, structure):
    ph_ran_with.append(spin)
    return 11.7


class EpsInputs(BaseModel):
    spin: Spin = Spin.NONE
    structure: str


@task.graph(input_model=EpsInputs)
def eps(spin, structure):
    return ph(spin=spin, structure=structure).result


def test_a_rule_on_the_inner_task_refuses_the_wiring_that_breaks_it():
    """The graph takes every spin; the rule is ph's own and fires where ph is wired.

    The value is refused at the line inside ``eps`` that hands it to ``ph``, so
    the graph is never built and no ``ph`` runs.
    """
    ph_ran_with.clear()
    with pytest.raises(TaskInputValidationError, match="noncollinear magnetism"):
        eps.build(spin=Spin.NON_COLLINEAR, structure="si")
    assert ph_ran_with == []


def test_a_spin_the_rule_admits_still_reaches_the_body_as_the_enum():
    """The control: the same wiring builds, runs, and hands the body the enum."""
    ph_ran_with.clear()
    graph = eps.build(spin=Spin.COLLINEAR, structure="si")
    assert "ph" in graph.tasks
    graph.run()
    assert ph_ran_with == [Spin.COLLINEAR]


@task()
def a_thousand():
    return 1000


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


def test_a_field_validator_does_not_fire_on_a_reference_at_the_call():
    """The boundary, pinned: a rule is not judged against a value that does not exist.

    A field written as a link is checked for its shape at the call and for its
    rule at the run edge, on what the link delivered.
    """
    with Graph(name="linked") as graph:
        source = a_thousand()
        capped(a=source.result, b=1)
    assert links_of(graph) == ["a_thousand.outputs.result -> capped.inputs.a"]


def test_the_rule_the_reference_escaped_fires_when_the_link_delivers():
    """The other half of the same claim: 1000 is refused, one checkpoint later."""
    with Graph(name="delivered") as graph:
        source = a_thousand()
        capped(a=source.result, b=1)
    with pytest.raises(TaskInputValidationError, match="at most 100"):
        graph.run()


def test_the_control_the_same_value_written_as_a_literal_is_refused_at_the_call():
    """What the reference bought: written plainly, the rule answers immediately."""
    with pytest.raises(TaskInputValidationError, match="at most 100"):
        with Graph(name="literal"):
            capped(a=1000, b=1)


def test_a_reference_nested_inside_a_value_leaves_the_whole_field_waiting():
    """A rule reads the field, so one member still to arrive holds the rule back."""

    class Weights(BaseModel):
        weights: dict[str, int]

        @field_validator("weights")
        @classmethod
        def _positive(cls, value):
            if any(item < 0 for item in value.values()):
                raise ValueError("every weight must be positive")
            return value

    @task(input_model=Weights)
    def weighted(weights):
        return sum(weights.values())

    with Graph(name="nested") as graph:
        source = a_thousand()
        weighted(weights={"a": -1, "b": source.result})
    assert graph.tasks["weighted"] is not None
    with pytest.raises(TaskInputValidationError, match="every weight must be positive"):
        with Graph(name="whole"):
            weighted(weights={"a": -1, "b": 2})


def test_the_private_name_the_rules_are_read_from_still_answers():
    """One canary: pydantic's decorator record is what the rule shadow is built from."""
    from node_graph.input_model import _own_field_validators

    decorators = Capped.__pydantic_decorators__.field_validators
    assert set(decorators) == {"cap"}
    assert decorators["cap"].info.mode == "after"
    assert decorators["cap"].info.fields == ("a",)
    assert set(_own_field_validators(Capped)) == {"cap"}


def test_a_model_validator_still_waits_for_the_run_edge():
    """A cross-field rule may read a field no one has written yet."""

    class Ordered(BaseModel):
        low: int
        high: int

        @model_validator(mode="after")
        def _ordered(self):
            if self.low >= self.high:
                raise ValueError("low must be below high")
            return self

    @task(input_model=Ordered)
    def ordered(low, high):
        return high - low

    graph = Graph(name="unordered")
    assert graph.add_task(ordered, "o", low=9, high=1) is not None
    with pytest.raises(TaskInputValidationError, match="low must be below high"):
        ordered.run(low=9, high=1)


#: What each field rule below was handed, in the order the rules ran.
#:
#: The models are written at module level so a task can name them: a task
#: carries a model it cannot import by value, and a copy's rule would write
#: to a copy of this list.
RULE_DATA: list = []


class Bounds(BaseModel):
    low: int
    high: int

    @field_validator("high")
    @classmethod
    def _above_low(cls, value, info):
        RULE_DATA.append(dict(info.data))
        if value <= info.data["low"]:
            raise ValueError("high must exceed low")
        return value


@task(input_model=Bounds)
def bounds(low, high):
    return high - low


def test_a_field_rule_reaching_for_a_sibling_waits_until_it_is_there():
    """A rule reading a field nobody wrote cannot be answered on that write.

    What the rule is handed is the discriminating part: the sibling is absent,
    so the lookup raises and the rule waits. A placeholder standing in for it
    would be judged instead, and judged wrong.
    """
    RULE_DATA.clear()

    graph = Graph(name="sibling")
    assert graph.add_task(bounds, "b", high=5) is not None
    assert RULE_DATA == [{}]
    with pytest.raises(TaskInputValidationError, match="high must exceed low"):
        bounds.run(low=9, high=5)
    assert RULE_DATA[-1] == {"low": 9}


class Flagged(BaseModel):
    strict: bool = False
    value: int = 0

    @field_validator("value")
    @classmethod
    def _capped_when_strict(cls, value, info):
        RULE_DATA.append(dict(info.data))
        if info.data.get("strict") and value > 10:
            raise ValueError("value is capped at 10 in strict mode")
        return value


@task(input_model=Flagged)
def flagged(strict, value):
    return value


def test_a_rule_reading_an_unwritten_sibling_reads_it_as_absent():
    """Absent, not defaulted and not a stand-in, so the rule answers as the model does."""
    RULE_DATA.clear()

    # The model's own verdict on the same write, which the wiring check must
    # not contradict: the default stands in only where the model itself runs.
    assert Flagged(value=99).value == 99
    assert RULE_DATA == [{"strict": False}]

    graph = Graph(name="flagged")
    assert graph.add_task(flagged, "f", value=99) is not None
    assert RULE_DATA[-1] == {}
    with pytest.raises(TaskInputValidationError, match="capped at 10"):
        graph.add_task(flagged, "g", strict=True, value=99)
    assert RULE_DATA[-1] == {"strict": True}


class Inner(BaseModel):
    n: int = 1

    def doubled(self) -> int:
        return self.n * 2


class Outer(BaseModel):
    inner: Inner = Inner()

    @field_validator("inner")
    @classmethod
    def _within_reach(cls, value):
        if not isinstance(value, Inner):
            raise ValueError("inner is not an Inner")
        if value.doubled() > 100:
            raise ValueError("inner.n is capped at 50")
        return value


@task(input_model=Outer)
def outer(inner):
    return inner


def test_a_rule_on_a_nested_field_gets_the_class_the_field_names():
    """It reads the value its field declares, so ``isinstance`` holds and methods answer."""
    graph = Graph(name="nested_ok")
    assert graph.add_task(outer, "a", inner={"n": 3}) is not None
    assert graph.add_task(outer, "b", inner=Inner(n=3)) is not None


def test_and_refuses_the_nested_value_the_model_refuses():
    """The other half: a rule that can read the instance can also judge it."""
    assert Outer(inner={"n": 3}).inner.n == 3
    with pytest.raises(ValidationError, match="capped at 50"):
        Outer(inner={"n": 999})
    graph = Graph(name="nested_bad")
    with pytest.raises(TaskInputValidationError, match="capped at 50"):
        graph.add_task(outer, "c", inner={"n": 999})


def test_a_link_deeper_than_the_walk_goes_leaves_the_field_waiting():
    """Unproved is not resolved: what the walk did not reach counts as awaiting a link."""
    from node_graph.input_model import _MAX_ANNOTATION_DEPTH

    class Deep(BaseModel):
        payload: Any = None

        @field_validator("payload")
        @classmethod
        def _bottoms_out_in_an_int(cls, value):
            innermost = value
            while isinstance(innermost, list) and innermost:
                innermost = innermost[0]
            if not isinstance(innermost, int):
                raise ValueError("payload must bottom out in an int")
            return value

    @task(input_model=Deep)
    def deep(payload):
        return payload

    graph = Graph(name="deep")
    source = graph.add_task(a_thousand, "s")
    # One list below where the walk stops, so the socket is never looked at.
    buried = source.outputs.result
    for _ in range(_MAX_ANNOTATION_DEPTH + 2):
        buried = [buried]
    assert graph.add_task(deep, "d", payload=buried) is not None
    assert graph.add_task(deep, "e", payload=[source.outputs.result]) is not None
    # The control: on a value with nothing left to arrive, the rule does run.
    with pytest.raises(TaskInputValidationError, match="bottom out in an int"):
        graph.add_task(deep, "f", payload=[["not an int"]])


def test_a_rule_on_an_aliased_field_fires_under_either_name():
    """A socket is named by its field, and a write naming the alias reaches it too."""

    class Priced(BaseModel):
        model_config = ConfigDict(populate_by_name=True)

        amount: int = Field(alias="qty")

        @field_validator("amount")
        @classmethod
        def _not_negative(cls, value):
            if value < 0:
                raise ValueError("amount cannot be negative")
            return value

    @task(input_model=Priced)
    def priced(amount):
        return amount

    graph = Graph(name="aliased_rule")
    with pytest.raises(TaskInputValidationError, match="cannot be negative"):
        graph.add_task(priced, "a", amount=-1)
    with pytest.raises(TaskInputValidationError, match="cannot be negative"):
        graph.add_task(priced, "b", qty=-1)
    assert graph.add_task(priced, "c", amount=5) is not None


def test_a_rewriting_field_validator_leaves_the_written_value_alone():
    """The rule runs on a copy: what was written is what reaches storage."""

    class Shouted(BaseModel):
        text: str

        @field_validator("text")
        @classmethod
        def _shout(cls, value):
            return value.upper()

    @task(input_model=Shouted)
    def shouted(text):
        return text

    graph = Graph(name="quiet")
    node = graph.add_task(shouted, "s", text="silicon")
    assert node.inputs.text.value == "silicon"


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
        lambda func, inputs, name: inputs,
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


def test_assigning_to_a_socket_writes_past_the_check():
    """The one write route the model does not reach, pinned so the claim cannot rot.

    The socket layer types ``amount`` as ``int`` and carries no ``gt=0``, so
    the assignment is refused by nothing and the value is stored;
    ``set_inputs`` refuses the same value.
    """
    graph = Graph(name="assigned")
    node = graph.add_task(bounded, "b")
    node.inputs.amount.value = -1
    assert node.inputs.amount.value == -1
    with pytest.raises(TaskInputValidationError, match="greater than 0"):
        node.set_inputs({"amount": -1})


def test_writing_only_some_of_the_fields_is_not_a_missing_input():
    """Inputs may be written a few at a time, and a link may supply the rest."""
    graph = Graph(name="partial")
    assert graph.add_task(bounded, "b") is not None
    assert graph.add_task(bounded, "c", amount=1) is not None


def test_a_task_written_into_an_input_is_a_reference_not_a_value():
    graph = Graph(name="linked")
    producer = graph.add_task(bounded, "p", amount=1)
    assert graph.add_task(bounded, "c", amount=producer.outputs.result) is not None


class Rated(BaseModel):
    """The rule is the model's own, so no socket type could carry it."""

    rating: int = 1

    @field_validator("rating")
    @classmethod
    def _in_range(cls, value):
        if not 1 <= value <= 5:
            raise ValueError("rating runs from 1 to 5")
        return value


@task(input_model=Rated)
def rated(rating):
    return rating


def test_a_field_rule_is_refused_when_it_is_passed_to_add_task():
    graph = Graph(name="rated_added")
    with pytest.raises(TaskInputValidationError, match="rating runs from 1 to 5"):
        graph.add_task(rated, "r", rating=9)


def test_a_field_rule_is_refused_when_it_is_set_on_the_task():
    graph = Graph(name="rated_set")
    node = graph.add_task(rated, "r")
    with pytest.raises(TaskInputValidationError, match="rating runs from 1 to 5"):
        node.set_inputs({"rating": 9})


def test_without_the_check_add_task_accepts_the_broken_rule(without_wiring_checks):
    """The control: the socket layer types ``rating`` as ``int`` and sees no rule."""
    graph = Graph(name="rated_unchecked")
    assert graph.add_task(rated, "r", rating=9) is not None


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


# --------------------------------------------------------------------------
# 20. A tag is judged by the value it carries
# --------------------------------------------------------------------------


class Cutoff(BaseModel):
    """A constraint and no rule, so only the type pass can enforce it."""

    structure: str
    ecutwfc: float = Field(default=60.0, le=200)


@task(input_model=Cutoff)
def cutoff(structure, ecutwfc):
    return ecutwfc


class CutoffCaller(BaseModel):
    structure: str = "si"
    ecutwfc: float = 60.0


@task.graph(input_model=CutoffCaller)
def calls_cutoff(structure, ecutwfc):
    return cutoff(structure=structure, ecutwfc=ecutwfc).result


def test_a_constraint_is_enforced_on_a_value_a_graph_body_passes_on():
    """A graph body hands its inputs on as tags, and a tag carries a value.

    The graph itself admits any cutoff; the bound is the leaf's own, and it is
    answered at the line inside the body that writes the value.
    """
    with pytest.raises(TaskInputValidationError, match="less than or equal to 200"):
        calls_cutoff.build(structure="si", ecutwfc=500)


def test_the_same_body_still_draws_the_link_for_a_value_the_bound_admits():
    """The control: judging the tag costs neither the build nor the link.

    A tag stripped to its value would leave the leaf holding a copy, so the
    link is what says the tag survived the check.
    """
    graph = calls_cutoff.build(structure="si", ecutwfc=100)
    assert "graph_inputs.inputs.ecutwfc -> cutoff.inputs.ecutwfc" in links_of(graph)


def test_a_tagged_value_and_the_value_it_carries_are_judged_alike():
    """The unit behind both: the type pass reads through the tag as the rules do."""
    from node_graph.socket import TaggedValue

    with Graph(name="tagged") as graph:
        source = a_thousand()

    tagged = TaggedValue(500, socket=source.result)
    for written in (500, tagged):
        with pytest.raises(TaskInputValidationError, match="less than or equal to 200"):
            validate_wiring_inputs(
                Cutoff, {"ecutwfc": written}, label="cutoff", complete=False
            )
    assert graph is not None


def test_a_bare_socket_in_the_same_place_is_still_a_reference():
    """The other half: what a link will deliver is not a value to judge."""
    with Graph(name="reference") as graph:
        source = a_thousand()
        cutoff(structure="si", ecutwfc=source.result)
    assert links_of(graph) == ["a_thousand.outputs.result -> cutoff.inputs.ecutwfc"]


# --------------------------------------------------------------------------
# 21. One rule waiting does not silence the rest of the write
# --------------------------------------------------------------------------


class Job(BaseModel):
    """Two rules, one of which reads a sibling."""

    low: int = 0
    high: int = 10
    cores: int = 1

    @field_validator("high")
    @classmethod
    def _above_low(cls, value, info):
        if value <= info.data["low"]:
            raise ValueError("high must exceed low")
        return value

    @field_validator("cores")
    @classmethod
    def _at_least_one(cls, value):
        if value < 1:
            raise ValueError("cores must be at least 1")
        return value


@task(input_model=Job)
def job(low, high, cores):
    return cores


def test_a_rule_waiting_for_a_sibling_leaves_its_neighbours_running():
    """``high``'s rule has no ``low`` to read; ``cores``'s rule is answerable."""
    graph = Graph(name="job")
    with pytest.raises(TaskInputValidationError, match="cores must be at least 1"):
        graph.add_task(job, "j", high=5, cores=-4)


def test_the_same_two_rules_still_answer_when_the_sibling_is_there():
    """The control: nothing waits, and the write is refused for the same reason."""
    graph = Graph(name="job_whole")
    with pytest.raises(TaskInputValidationError, match="cores must be at least 1"):
        graph.add_task(job, "j", low=0, high=5, cores=-4)


def test_the_rule_that_waited_is_answered_at_the_run_edge():
    """The other half: what waits is judged once the whole payload is in hand."""
    with pytest.raises(TaskInputValidationError, match="high must exceed low"):
        job.run(low=9, high=5, cores=1)


#: The table the rule below reads, so a missing key is the rule's own error.
KNOWN_KEYS = {"a": 1}


class Keyed(BaseModel):
    key: str = "a"
    other: int = 0

    @field_validator("key")
    @classmethod
    def _known(cls, value):
        KNOWN_KEYS[value]
        return value

    @field_validator("other")
    @classmethod
    def _positive(cls, value):
        if value < 0:
            raise ValueError("other must be positive")
        return value


@task(input_model=Keyed)
def keyed(key, other):
    return key


def test_a_key_error_of_the_rules_own_making_refuses_the_write():
    """A rule that raises is a rule that answered, whatever it raised.

    The model itself raises ``KeyError`` on the same value, so a write the
    wiring check waves through would be a write the model refuses.
    """
    with pytest.raises(KeyError):
        Keyed(key="zzz")
    graph = Graph(name="keyed")
    with pytest.raises(KeyError):
        graph.add_task(keyed, "k", key="zzz")


def test_that_rule_does_not_silence_the_write_it_shares():
    """The control: the neighbouring rule is reached on a key the table has."""
    graph = Graph(name="keyed_ok")
    with pytest.raises(TaskInputValidationError, match="other must be positive"):
        graph.add_task(keyed, "k", key="a", other=-1)


# --------------------------------------------------------------------------
# 22. A nested model's cross-field rule waits too
# --------------------------------------------------------------------------


class Agreeing(BaseModel):
    n: int = 1
    m: int = 1

    @model_validator(mode="after")
    def _agree(self):
        if self.n != self.m:
            raise ValueError("n and m must agree")
        return self


class HoldsAgreeing(BaseModel):
    """No rule of its own, so nothing of this model's runs at a write."""

    pair: Agreeing = Agreeing()
    note: str = "x"


class HoldsAgreeingAndARule(BaseModel):
    """The same shape with one field rule, unrelated to the nested model."""

    pair: Agreeing = Agreeing()
    note: str = "x"

    @field_validator("note")
    @classmethod
    def _short(cls, value):
        if len(value) > 10:
            raise ValueError("note is capped at 10")
        return value


@task(input_model=HoldsAgreeing)
def holds_agreeing(pair, note):
    return note


@task(input_model=HoldsAgreeingAndARule)
def holds_agreeing_and_a_rule(pair, note):
    return note


@pytest.mark.parametrize(
    "handle", [holds_agreeing, holds_agreeing_and_a_rule], ids=["bare", "ruled"]
)
def test_a_nested_cross_field_rule_waits_whatever_else_the_model_carries(handle):
    """A write is a write: what the outer model happens to declare cannot decide it.

    The nested rule may read a field a later write or a link supplies, so it
    waits exactly as the outer model's own cross-field rules do.
    """
    graph = Graph(name=f"nested_{handle.identifier}")
    assert graph.add_task(handle, "h", pair={"n": 1, "m": 2}) is not None


@pytest.mark.parametrize(
    "handle", [holds_agreeing, holds_agreeing_and_a_rule], ids=["bare", "ruled"]
)
def test_the_same_nested_rule_is_answered_at_the_run_edge(handle):
    """The other half: the rule is enforced, one checkpoint later, in both models."""
    with pytest.raises(TaskInputValidationError, match="n and m must agree"):
        handle.run(pair={"n": 1, "m": 2}, note="x")


def test_a_field_rule_inside_a_nested_model_still_runs_at_the_write():
    """What waits is the cross-field rule; a rule on one field is answerable."""

    class Capped(BaseModel):
        n: int = 1

        @field_validator("n")
        @classmethod
        def _small(cls, value):
            if value > 100:
                raise ValueError("n is capped at 100")
            return value

    class HoldsCapped(BaseModel):
        inner: Capped = Capped()

    @task(input_model=HoldsCapped)
    def holds_capped(inner):
        return inner

    graph = Graph(name="nested_field_rule")
    with pytest.raises(TaskInputValidationError, match="n is capped at 100"):
        graph.add_task(holds_capped, "h", inner={"n": 999})
    assert graph.add_task(holds_capped, "ok", inner={"n": 3}) is not None


def test_the_private_name_a_models_cross_field_rules_are_read_from_still_answers():
    """One canary: the twin is the model with that record emptied, and only there."""
    from node_graph.input_model import _field_rules_only

    assert set(Agreeing.__pydantic_decorators__.model_validators) == {"_agree"}
    twin = _field_rules_only(Agreeing)
    assert issubclass(twin, Agreeing)
    assert twin.__pydantic_decorators__.model_validators == {}
    assert set(Agreeing.__pydantic_decorators__.model_validators) == {"_agree"}


# --------------------------------------------------------------------------
# 23. A model this process cannot read is not a task without rules
# --------------------------------------------------------------------------


class _RaisingExecutor:
    """An executor whose callable cannot be produced."""

    def __init__(self, error: Exception) -> None:
        self._error = error

    @property
    def callable(self):
        raise self._error


class _SpecWith:
    def __init__(self, executor) -> None:
        self.executor = executor


class _TaskWith:
    def __init__(self, executor) -> None:
        self.name = "t"
        self.spec = _SpecWith(executor)


def test_a_callable_this_process_cannot_rebuild_is_refused_by_name():
    """Reading the model is how the checks are found; failing to read it is loud."""
    from node_graph.input_model import _input_model_of_task

    task_like = _TaskWith(_RaisingExecutor(RuntimeError("no schema")))
    with pytest.raises(ModelContractError, match="importable module"):
        _input_model_of_task(task_like)


def test_a_callable_that_is_simply_not_here_still_has_no_contract():
    """The control, and the documented case: nothing to import is nothing to enforce."""
    from node_graph.input_model import _input_model_of_task

    task_like = _TaskWith(_RaisingExecutor(ImportError("no such module")))
    assert _input_model_of_task(task_like) is None


def test_a_task_whose_callable_is_here_reads_its_model():
    """The other control: the ordinary path still finds the model it enforces."""
    from node_graph.input_model import _input_model_of_task

    graph = Graph(name="resolves")
    assert _input_model_of_task(graph.add_task(bounded, "b")) is Bounded


def test_a_model_written_in_a_script_that_cannot_be_rebuilt_is_refused(tmp_path):
    """The route this reaches in practice, run as a script rather than described.

    Under ``from __future__ import annotations``, a model declaring a nested
    model that carries a ``@model_validator`` does not survive the round trip
    a ``__main__`` callable is stored through, and a model that cannot be read
    is a task whose every write would go unchecked.
    """
    import subprocess
    import sys

    script = tmp_path / "run.py"
    script.write_text(
        "from __future__ import annotations\n"
        "from pydantic import BaseModel, model_validator\n"
        "from node_graph import Graph, task\n"
        "\n"
        "class Pair(BaseModel):\n"
        "    n: int = 1\n"
        "    m: int = 1\n"
        "    @model_validator(mode='after')\n"
        "    def _agree(self):\n"
        "        if self.n != self.m:\n"
        "            raise ValueError('n and m must agree')\n"
        "        return self\n"
        "\n"
        "class Holder(BaseModel):\n"
        "    pair: Pair = Pair()\n"
        "\n"
        "@task(input_model=Holder)\n"
        "def holder(pair):\n"
        "    return pair\n"
        "\n"
        "Graph(name='s').add_task(holder, 'h')\n"
    )
    finished = subprocess.run(
        [sys.executable, str(script)], capture_output=True, text=True
    )
    assert finished.returncode != 0
    assert "ModelContractError" in finished.stderr
    assert "importable module" in finished.stderr


# --------------------------------------------------------------------------
# 24. A socket refusal and a model refusal address the same value alike
# --------------------------------------------------------------------------


class Control(BaseModel):
    model_config = ConfigDict(extra="forbid")

    calculation: Literal["nscf"] = "nscf"


class Parameters(BaseModel):
    CONTROL: Control = Control()


class Forced(BaseModel):
    """A namelist whose one keyword the route decides, so no field declares it."""

    model_config = ConfigDict(extra="forbid")


class Overrides(BaseModel):
    nscf: Forced = Forced()


class RouteInputs(BaseModel):
    parameters: Parameters = Parameters()
    overrides: Overrides = Overrides()


@task(input_model=RouteInputs)
def route_leaf(parameters, overrides):
    return 1


@task.graph(input_model=RouteInputs)
def route(parameters, overrides):
    return route_leaf(parameters=parameters, overrides=overrides).result


@pytest.mark.parametrize(
    "written, loc, error_type",
    [
        (
            {"parameters": {"CONTROL": {"calculation": "scf"}}},
            ("parameters", "CONTROL", "calculation"),
            "literal_error",
        ),
        (
            {"overrides": {"nscf": {"nosym": False}}},
            ("overrides", "nscf", "nosym"),
            "extra_forbidden",
        ),
    ],
    ids=["outside the literal", "no field to write to"],
)
def test_a_graphs_own_input_is_refused_with_the_path_that_was_refused(
    written, loc, error_type
):
    """A graph's own inputs are written into sockets, and a socket says where.

    Written into the graph, the value never reaches a model: the refusal comes
    from the socket layer, which now carries the same two facts a model's
    refusal carries.
    """
    from node_graph.errors import SocketValueError

    with pytest.raises(SocketValueError) as caught:
        route.build(**written)
    assert caught.value.loc == loc
    assert caught.value.type == error_type


@pytest.mark.parametrize(
    "written, loc",
    [
        (
            {"parameters": {"CONTROL": {"calculation": "scf"}}},
            ("parameters", "CONTROL", "calculation"),
        ),
        (
            {"overrides": {"nscf": {"nosym": False}}},
            ("overrides", "nscf", "nosym"),
        ),
    ],
    ids=["outside the literal", "no field to write to"],
)
def test_the_model_refuses_the_same_write_at_the_same_path(written, loc):
    """The reference: what the leaf's model says about the same two writes."""
    graph = Graph(name="model_side")
    with pytest.raises(TaskInputValidationError) as caught:
        graph.add_task(route_leaf, "leaf", **written)
    assert [error["loc"] for error in caught.value.__cause__.errors()] == [loc]


@pytest.mark.parametrize(
    "written, loc, error_type",
    [
        (
            {"parameters": {"CONTROL": {"calculation": "scf"}}},
            ("parameters", "CONTROL", "calculation"),
            "literal_error",
        ),
        (
            {"overrides": {"nscf": {"nosym": False}}},
            ("overrides", "nscf", "nosym"),
            "extra_forbidden",
        ),
    ],
    ids=["outside the literal", "no field to write to"],
)
def test_a_models_refusal_is_read_the_way_a_sockets_is(written, loc, error_type):
    """Where and why, off the refusal itself: neither caller parses a message."""
    graph = Graph(name="model_side_read")
    with pytest.raises(TaskInputValidationError) as caught:
        graph.add_task(route_leaf, "leaf", **written)
    assert [(error["loc"], error["type"]) for error in caught.value.errors] == [
        (loc, error_type)
    ]
    assert caught.value.task == "leaf"
    assert caught.value.model is RouteInputs


def test_a_refusal_raised_with_no_report_behind_it_still_answers():
    """The attributes are there to read whether or not pydantic filled them."""
    refusal = TaskInputValidationError("nothing pydantic said")
    assert refusal.errors == []
    assert refusal.task == ""
    assert refusal.model is None


def test_a_socket_refusal_is_still_a_value_error():
    """The carrier is added to the refusal, not put in place of it."""
    from node_graph.errors import SocketValueError

    assert issubclass(SocketValueError, ValueError)
    with pytest.raises(ValueError):
        route.build(parameters={"CONTROL": {"calculation": "scf"}})


# --------------------------------------------------------------------------
# 25. A graph body is handed the types its model declares
# --------------------------------------------------------------------------


#: What the graph bodies below were handed, read back after the build.
BODY_SAW: dict = {}


class SpinInputs(BaseModel):
    spin: Color = Color.RED
    ratio: Decimal = Decimal("0.10")


@task.graph(input_model=SpinInputs)
def spun(spin, ratio):
    BODY_SAW["spin"] = spin
    BODY_SAW["ratio"] = ratio
    return add(x=1, y=2)


def test_a_graph_body_is_handed_the_member_its_field_declares():
    """The body runs the model's rules, so it should run on the model's values."""
    BODY_SAW.clear()
    spun.build(spin="blue", ratio="0.25")
    assert BODY_SAW["spin"] == Color.BLUE
    assert BODY_SAW["spin"] in (Color.RED, Color.BLUE)
    assert BODY_SAW["ratio"] == Decimal("0.25")


def test_the_rebuilt_value_still_carries_the_tag_its_link_is_drawn_from():
    """The control: rebuilding a value must not cost the body its link."""
    from node_graph.socket import TaggedValue

    BODY_SAW.clear()
    graph = spun.build(spin="blue", ratio="0.25")
    assert isinstance(BODY_SAW["spin"], TaggedValue)
    assert "add.outputs.result -> graph_outputs.outputs.result" in links_of(graph)


class NestedSpin(BaseModel):
    spin: Color = Color.RED


class HoldsNestedSpin(BaseModel):
    inner: NestedSpin = NestedSpin()
    ratio: Decimal = Decimal("0.10")


@task.graph(input_model=HoldsNestedSpin)
def nested_spun(inner, ratio):
    BODY_SAW["inner"] = inner
    return add(x=1, y=2)


def test_a_member_below_a_namespace_is_rebuilt_and_still_tagged():
    """A namespace's members carry tags of their own, so the walk goes in."""
    from node_graph.socket import TaggedValue

    BODY_SAW.clear()
    nested_spun.build(inner={"spin": "blue"}, ratio="0.25")
    assert BODY_SAW["inner"]["spin"] == Color.BLUE
    assert isinstance(BODY_SAW["inner"]["spin"], TaggedValue)


# --------------------------------------------------------------------------
# 26. A model that names itself
# --------------------------------------------------------------------------


class Chain(BaseModel):
    """A model whose field names the model itself."""

    n: int = 0
    next: Optional["Chain"] = None

    @field_validator("n")
    @classmethod
    def _small(cls, value):
        if value > 10:
            raise ValueError("n is capped at 10")
        return value


Chain.model_rebuild()


def test_a_model_that_names_itself_is_refused_where_it_is_declared():
    """A namespace holds one socket per field, and this one has no bottom.

    Nothing else could answer: the walk that builds the sockets, and every
    rebuild the checkpoints make, would each follow the chain forever.
    """
    with pytest.raises(ModelContractError, match="Chain -> Chain"):

        @task(input_model=Chain)
        def chained(n, next):
            return n


def test_the_same_model_one_link_shorter_is_a_namespace_with_a_bottom():
    """The control: what is refused is the cycle, not the nesting."""

    class Link(BaseModel):
        n: int = 0

    class Head(BaseModel):
        n: int = 0
        next: Optional[Link] = None

    @task(input_model=Head)
    def headed(n, next):
        return n

    graph = Graph(name="headed")
    assert graph.add_task(headed, "h", n=1, next={"n": 2}) is not None


def test_the_shadows_a_write_is_judged_by_end_at_the_same_bound():
    """The rebuilds terminate on their own, so no other entry point can hang."""
    validate_wiring_inputs(Chain, {"n": 1, "next": {"n": 2}}, label="c", complete=False)
    with pytest.raises(TaskInputValidationError, match="n is capped at 10"):
        validate_wiring_inputs(Chain, {"n": 99}, label="c", complete=False)


# --------------------------------------------------------------------------
# 27. A handle that does not take the name of the function it decorates
# --------------------------------------------------------------------------


class BandCount(BaseModel):
    """A rule no socket type check can stand in for."""

    nbnd: int = 1

    @field_validator("nbnd")
    @classmethod
    def _counted(cls, value):
        if value < 0:
            raise ValueError("nbnd counts bands, so it cannot be negative")
        return value


class BandCap(BaseModel):
    """The opposite rule on the same field, for a second task off one function."""

    nbnd: int = 1

    @field_validator("nbnd")
    @classmethod
    def _capped(cls, value):
        if value > 10:
            raise ValueError("nbnd is capped at 10")
        return value


def _band_body(nbnd):
    return nbnd


#: The decorated name is never rebound, so the module still binds the function.
counted_bands = task(input_model=BandCount)(_band_body)
capped_bands = task(input_model=BandCap)(_band_body)


@task(input_model=BandCount)
def rebound_bands(nbnd):
    """The ordinary spelling: the handle replaces the module global."""
    return nbnd


@pytest.mark.parametrize(
    "handle",
    [counted_bands, rebound_bands],
    ids=["handle named apart", "handle rebound to the name"],
)
def test_the_run_edge_holds_the_model_whatever_the_handle_is_called(handle):
    """The body runs through the executor, and the executor must reach the wrapper."""
    with pytest.raises(TaskInputValidationError, match="cannot be negative"):
        handle.run(nbnd=-5)


@pytest.mark.parametrize(
    "handle",
    [counted_bands, rebound_bands],
    ids=["handle named apart", "handle rebound to the name"],
)
def test_the_write_reads_the_model_by_the_same_route(handle):
    """The write checkpoint finds the model through the same executor."""
    graph = Graph(name="named_apart")
    with pytest.raises(TaskInputValidationError, match="cannot be negative"):
        graph.add_task(handle, "b", nbnd=-5)


def test_the_function_itself_is_left_unstamped():
    """What is bound is the wrapper: the function still enforces nothing."""
    from node_graph.input_model import input_model_of_callable

    assert input_model_of_callable(_band_body) is None
    assert input_model_of_callable(counted_bands._spec.executor.callable) is BandCount


def test_the_wrapper_keeps_the_name_a_process_is_labelled_with():
    """Only the name the executor records changes, not the name of the callable."""
    executor = counted_bands._spec.executor
    assert executor.callable_name != "_band_body"
    assert executor.callable.__name__ == "_band_body"


def test_two_tasks_off_one_function_each_keep_their_own_model():
    """Two wrappers cannot answer to one name, so each is bound under its own."""
    assert counted_bands.run(nbnd=20) == 20
    with pytest.raises(TaskInputValidationError, match="capped at 10"):
        capped_bands.run(nbnd=20)
    with pytest.raises(TaskInputValidationError, match="cannot be negative"):
        counted_bands.run(nbnd=-5)


def test_a_wrapper_stored_by_value_carries_its_model_with_it():
    """The other route out of this module: nothing to bind, and nothing lost."""

    def nested(nbnd):
        return nbnd

    handle = task(input_model=BandCount)(nested)
    assert handle._spec.executor.mode.value == "pickled_callable"
    with pytest.raises(TaskInputValidationError, match="cannot be negative"):
        handle.run(nbnd=-5)


