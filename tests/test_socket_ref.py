"""Socket references for namespace members in eager graph bodies."""

from __future__ import annotations

from typing import Any, NotRequired, TypedDict

import pytest

from node_graph import Graph, task
from node_graph.engine.local import LocalEngine
from node_graph.socket import SocketReference, TaggedNamespace
from node_graph.socket_spec import namespace as ns


class Codes(TypedDict):
    pw: Any
    ph: NotRequired[Any]


@task()
def run_code(code: Any) -> str:
    return f"ran {code}"


@task()
def maybe_run_code(code: Any = None) -> str:
    return f"ran {code}"


def sink_of(graph: Graph, task_name: str = "run_code"):
    return graph.tasks[task_name].inputs.code


def link_sources(socket) -> list[str]:
    return [
        f"{link.from_task.name}.{link.from_socket._scoped_name}"
        for link in socket._links
    ]


# Graph bodies run against a re-imported function object, so they report back
# through module state rather than a closure.
SEEN: dict[str, Any] = {}


@task.graph()
def Inspect(codes: Codes):
    SEEN["codes"] = codes
    SEEN["ref"] = codes.ref("ph")
    SEEN["subscript_error"] = None
    try:
        codes["ph"]
    except KeyError as exc:
        SEEN["subscript_error"] = exc


def test_body_receives_tagged_namespace():
    """A namespace input arrives as a mapping that knows its own socket."""
    Inspect.build(codes={"pw": "PW", "ph": "PH"})
    assert isinstance(SEEN["codes"], TaggedNamespace)
    assert SEEN["codes"]["pw"] == "PW"
    assert SEEN["codes"]._socket._name == "codes"


def test_ref_does_not_raise_for_an_absent_member():
    """``ref`` returns a reference where subscription raises ``KeyError``."""
    Inspect.build(codes={"pw": "PW"})
    assert isinstance(SEEN["ref"], SocketReference)
    assert SEEN["ref"].is_provided() is False
    assert isinstance(SEEN["subscript_error"], KeyError)


def test_ref_links_a_provided_member():
    """A provided member links exactly as subscription does, and its value flows."""

    @task.graph()
    def ByRef(codes: Codes):
        run_code(code=codes.ref("ph"))

    @task.graph()
    def BySubscript(codes: Codes):
        run_code(code=codes["ph"])

    by_ref = ByRef.build(codes={"pw": "PW", "ph": "PH"})
    by_subscript = BySubscript.build(codes={"pw": "PW", "ph": "PH"})

    assert link_sources(sink_of(by_ref)) == ["graph_inputs.codes.ph"]
    assert link_sources(sink_of(by_ref)) == link_sources(sink_of(by_subscript))
    assert "unresolved_ref" not in sink_of(by_ref)._metadata.extras


def test_ref_value_flows_at_run_time():
    """The referenced value reaches the task that consumes it."""

    @task.graph(outputs=ns(out=Any))
    def ByRef(codes: Codes):
        out = run_code(code=codes.ref("ph"))
        return {"out": out.result}

    graph = ByRef.build(codes={"pw": "PW", "ph": "PH"})
    assert LocalEngine().run(graph)["out"] == "ran PH"


def test_absent_member_leaves_a_required_socket_unfilled():
    """An absent member leaves the consuming socket unfilled, so a checker can see it."""

    @task.graph()
    def ByRef(codes: Codes):
        run_code(code=codes.ref("ph"))

    graph = ByRef.build(codes={"pw": "PW"})
    sink = sink_of(graph)
    assert sink._links == []
    assert sink.value is None
    assert sink._metadata.required is True
    assert sink._metadata.extras["unresolved_ref"] == "graph_inputs.codes.ph"


def test_absent_member_leaves_an_optional_socket_unset():
    """An absent member wired into an optional socket is not an error."""

    @task.graph()
    def ByRef(codes: Codes):
        maybe_run_code(code=codes.ref("ph"))

    graph = ByRef.build(codes={"pw": "PW"})
    sink = sink_of(graph, "maybe_run_code")
    assert sink._links == []
    assert sink._metadata.required is False
    assert sink._metadata.extras["unresolved_ref"] == "graph_inputs.codes.ph"


def test_required_namespace_reaches_the_body_when_empty():
    """A required namespace is passed to the body even with no member provided."""

    @task.graph()
    def ByRef(codes: Codes):
        run_code(code=codes.ref("pw"))

    graph = ByRef.build(codes={})
    assert sink_of(graph)._metadata.extras["unresolved_ref"] == "graph_inputs.codes.pw"


def test_ref_reaches_a_nested_member():
    """Dotted names reference members of nested namespaces."""

    @task.graph()
    def ByRef(config: ns(codes=ns(pw=Any))):
        run_code(code=config.ref("codes.pw"))

    provided = ByRef.build(config={"codes": {"pw": "PW"}})
    assert link_sources(sink_of(provided)) == ["graph_inputs.config.codes.pw"]

    absent = ByRef.build(config={"codes": {}})
    assert (
        sink_of(absent)._metadata.extras["unresolved_ref"]
        == "graph_inputs.config.codes.pw"
    )


def test_ref_inside_a_namespace_assignment():
    """A reference can be handed over as one member of a namespace input."""

    @task()
    def add(data: ns(x=int, y=int)) -> int:
        return data["x"] + data["y"]

    @task.graph()
    def ByRef(numbers: ns(x=int, y=NotRequired[int])):
        add(data={"x": numbers.ref("x"), "y": numbers.ref("y")})

    graph = ByRef.build(numbers={"x": 1})
    sink = graph.tasks["add"].inputs.data
    assert link_sources(sink.x) == ["graph_inputs.numbers.x"]
    assert sink.y._links == []
    assert sink.y._metadata.extras["unresolved_ref"] == "graph_inputs.numbers.y"


def test_ref_to_an_undeclared_member_raises():
    """Referencing a member the namespace does not declare fails at build."""

    @task.graph()
    def ByRef(codes: Codes):
        run_code(code=codes.ref("nope"))

    with pytest.raises(ValueError, match="not a member of namespace"):
        ByRef.build(codes={"pw": "PW"})


def test_subscription_is_unchanged():
    """Subscription still returns values and still raises for absent members."""

    @task.graph()
    def BySubscript(codes: Codes):
        run_code(code=codes["ph"])

    with pytest.raises(KeyError):
        BySubscript.build(codes={"pw": "PW"})


def test_graph_round_trips_with_a_reference():
    """to_dict/from_dict preserves both a resolved link and an unresolved reference."""

    @task.graph()
    def ByRef(codes: Codes):
        run_code(code=codes.ref("ph"))

    provided = Graph.from_dict(ByRef.build(codes={"pw": "PW", "ph": "PH"}).to_dict())
    assert link_sources(sink_of(provided)) == ["graph_inputs.codes.ph"]

    absent = Graph.from_dict(ByRef.build(codes={"pw": "PW"}).to_dict())
    assert sink_of(absent)._links == []
    assert sink_of(absent)._metadata.extras["unresolved_ref"] == "graph_inputs.codes.ph"
