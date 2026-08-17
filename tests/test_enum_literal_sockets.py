"""An enum or Literal socket accepts what names one of its members, nothing else."""

from enum import Enum
from typing import Literal, Optional

import pytest

from node_graph import Graph, task
from node_graph.engine.local import LocalEngine
from node_graph.socket_spec import SocketSpecAPI as api


class Spin(Enum):
    NONE = "none"
    COLLINEAR = "collinear"
    SPIN_ORBIT = "spin_orbit"


class Narrow(Enum):
    """A separate enum whose members repeat two of ``Spin``'s values."""

    NONE = "none"
    COLLINEAR = "collinear"


class NameOnly(Enum):
    """Shares a member NAME with ``Narrow``, but not its value."""

    NONE = "something_else"


@task()
def consume_narrow(spin: Narrow) -> str:
    assert isinstance(spin, Narrow), f"expected Narrow, got {type(spin).__name__}"
    return spin.value


@task.graph()
def narrow_graph(spin: Narrow) -> str:
    return consume_narrow(spin=spin).result


@task.graph()
def defer_literal(spin) -> str:
    """Call the enum-typed sub-graph with whatever the parent was given."""
    return narrow_graph(spin=spin)


ACCEPTED = [
    pytest.param(Narrow.NONE, id="declared-member"),
    pytest.param(Spin.NONE, id="foreign-member-same-value"),
    pytest.param("none", id="bare-value"),
]

REJECTED = [
    pytest.param("banana", id="unknown-value"),
    pytest.param(Spin.SPIN_ORBIT, id="foreign-member-unknown-value"),
    pytest.param(NameOnly.NONE, id="foreign-member-matching-name-only"),
    pytest.param(42, id="wrong-type"),
]


@pytest.mark.parametrize("value", ACCEPTED)
def test_entry_graph_accepts_anything_naming_a_member(value):
    ng = narrow_graph.build(spin=value)

    assert ng.inputs.spin.value == Narrow.NONE


@pytest.mark.parametrize("value", REJECTED)
def test_entry_graph_rejects_a_value_naming_no_member(value):
    with pytest.raises(ValueError, match="Input should be 'none' or 'collinear'"):
        narrow_graph.build(spin=value)


@pytest.mark.parametrize("value", ACCEPTED)
def test_deferred_subgraph_accepts_anything_naming_a_member(value):
    @task.graph()
    def outer() -> str:
        return narrow_graph(spin=value)

    ng = outer.build()

    assert ng.tasks.narrow_graph.inputs.spin.value == Narrow.NONE


@pytest.mark.parametrize("value", REJECTED)
def test_deferred_subgraph_rejects_at_build_not_at_run(value):
    @task.graph()
    def outer() -> str:
        return narrow_graph(spin=value)

    with pytest.raises(ValueError, match="Input should be 'none' or 'collinear'"):
        outer.build()


@pytest.mark.parametrize("value", REJECTED)
def test_link_from_untyped_parent_socket_rejects_at_build(value):
    """The parent socket is untyped, so the link is where the value is read."""
    with pytest.raises(ValueError, match="Input should be 'none' or 'collinear'"):
        defer_literal.build(spin=value)


def test_error_names_the_socket_and_omits_the_value_wrapper():
    with pytest.raises(ValueError) as excinfo:
        narrow_graph.build(spin="banana")

    message = str(excinfo.value)
    assert "graph_inputs.inputs.spin" in message
    assert "TaggedValue" not in message
    assert "uuid" not in message


def test_body_receives_a_member_rebuilt_from_the_stored_value():
    """A run stores the bare value; the body still sees the member."""
    ng = Graph(name="enum-readback")
    node = ng.add_task(consume_narrow, "pick", spin=Spin.COLLINEAR)
    ng.outputs.result = node.outputs.result

    results = LocalEngine().run(ng)

    assert results["result"] == "collinear"


def test_an_enum_parameter_keeps_the_requiredness_of_its_default():
    def signature(a: Spin, b: Spin = Spin.NONE, c: Optional[Spin] = None):
        ...

    fields = api.build_inputs_from_signature(signature).fields

    assert fields["a"].meta.required is True
    assert fields["b"].meta.required is False
    assert fields["b"].default is Spin.NONE
    assert fields["c"].meta.required is False


def test_optional_enum_socket_still_takes_none():
    @task.graph()
    def maybe(spin: Narrow = None) -> str:
        return consume_narrow(spin=Narrow.NONE).result

    ng = maybe.build(spin=None)

    assert ng.inputs.spin.value is None


# --- Literal ---------------------------------------------------------------


def test_literal_of_enum_members_carries_the_enum_and_the_subset():
    spec = api._leaf_from_type(Literal[Spin.NONE, Spin.COLLINEAR])

    assert spec.meta.extras["allowed_values"] == ["none", "collinear"]
    assert spec.meta.extras["structured_type"]["kind"] == "enum"
    assert spec.meta.extras["structured_type"]["path"].endswith(".Spin")


def test_literal_of_strings_carries_its_base_type():
    spec = api._leaf_from_type(Literal["none", "collinear"])

    assert spec.meta.extras["allowed_values"] == ["none", "collinear"]
    assert spec.meta.extras["literal_base"] == api._leaf_from_type(str).identifier
    assert "structured_type" not in spec.meta.extras


def test_literal_of_mixed_types_keeps_the_values_without_a_base_type():
    spec = api._leaf_from_type(Literal["a", 1])

    assert spec.meta.extras["allowed_values"] == ["a", 1]
    assert "literal_base" not in spec.meta.extras


def test_literal_of_unrepresentable_arguments_constrains_nothing():
    spec = api._leaf_from_type(Literal[b"x"])

    assert "allowed_values" not in spec.meta.extras


def test_py_type_name_distinguishes_two_literals():
    assert api._py_type_name(Literal[1, 2]) != api._py_type_name(Literal["a", "b"])
    assert api._py_type_name(Literal["a", "b"]) == "typing.Literal['a', 'b']"


def test_literal_socket_takes_a_member_of_its_subset_by_value():
    @task.graph()
    def only_none(spin: Literal[Spin.NONE]) -> str:
        return consume_narrow(spin=Narrow.NONE).result

    assert only_none.build(spin="none").inputs.spin.value == Spin.NONE
    assert only_none.build(spin=Narrow.NONE).inputs.spin.value == Spin.NONE
    with pytest.raises(ValueError, match="Input should be 'none'"):
        only_none.build(spin=Spin.COLLINEAR)


# --- links -----------------------------------------------------------------


@task()
def emit_subset() -> Literal[Spin.NONE, Spin.COLLINEAR]:
    return Spin.NONE


@task()
def emit_spin() -> Spin:
    return Spin.NONE


@task()
def emit_ints() -> Literal[1, 2]:
    return 1


@task()
def emit_one_string() -> Literal["none"]:
    return "none"


@task()
def take_spin(x: Spin) -> int:
    return 1


@task()
def take_subset(x: Literal[Spin.NONE, Spin.COLLINEAR]) -> int:
    return 1


@task()
def take_strings(x: Literal["none", "collinear"]) -> int:
    return 1


@task()
def take_str(x: str) -> int:
    return 1


def link(producer, consumer):
    ng = Graph(name="link")
    src = ng.add_task(producer, "src")
    dst = ng.add_task(consumer, "dst")
    ng.add_link(src.outputs.result, dst.inputs.x)


def test_a_subset_flows_into_the_whole_enum():
    link(emit_subset, take_spin)


def test_the_whole_enum_does_not_flow_into_a_subset():
    with pytest.raises(TypeError, match="Socket value range mismatch"):
        link(emit_spin, take_subset)


def test_a_subset_flows_into_another_enum_carrying_the_same_values():
    """Membership is by value, so the declaring class need not match."""

    @task()
    def take_narrow_enum(x: Narrow) -> int:
        return 1

    link(emit_subset, take_narrow_enum)


def test_literals_of_different_base_types_do_not_mix():
    with pytest.raises(TypeError, match="Socket value range mismatch"):
        link(emit_ints, take_strings)


def test_a_string_subset_flows_into_a_wider_string_literal():
    link(emit_one_string, take_strings)


def test_a_string_literal_widens_into_its_base_type():
    link(emit_one_string, take_str)


def test_an_unrestricted_source_does_not_flow_into_a_literal():
    with pytest.raises(TypeError, match="Socket value range mismatch"):
        link(take_str, take_strings)
