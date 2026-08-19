"""Socket references for namespace members in eager graph bodies.

No ``from __future__ import annotations`` here: the graph signatures below
use ``ns(...)`` specs in annotation position, which postponed evaluation
turns into strings that Python 3.10's forward-reference evaluation rejects
(a spec instance is not a type).
"""

from typing import Any, TypedDict

try:
    from typing import NotRequired
except ImportError:  # pragma: no cover - Python < 3.11
    from typing_extensions import NotRequired

import pytest

from node_graph import Graph, reference, task
from node_graph.engine.local import LocalEngine
from node_graph.socket import SocketReference, TaggedNamespace, socket_is_provided
from node_graph.socket_spec import namespace as ns


class Codes(TypedDict):
    pw: Any
    ph: NotRequired[Any]


class Options(TypedDict, total=False):
    """A required namespace whose every member is optional."""

    ph: Any
    projwfc: Any


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
    SEEN["reference"] = codes.reference("ph")
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


def test_reference_does_not_raise_for_an_absent_member():
    """``reference`` returns a reference where subscription raises ``KeyError``."""
    Inspect.build(codes={"pw": "PW"})
    assert isinstance(SEEN["reference"], SocketReference)
    assert SEEN["reference"].is_provided() is False
    assert isinstance(SEEN["subscript_error"], KeyError)


def test_reference_links_a_provided_member():
    """A provided member links exactly as subscription does, and its value flows."""

    @task.graph()
    def ByReference(codes: Codes):
        run_code(code=codes.reference("ph"))

    @task.graph()
    def BySubscript(codes: Codes):
        run_code(code=codes["ph"])

    by_reference = ByReference.build(codes={"pw": "PW", "ph": "PH"})
    by_subscript = BySubscript.build(codes={"pw": "PW", "ph": "PH"})

    assert link_sources(sink_of(by_reference)) == ["graph_inputs.codes.ph"]
    assert link_sources(sink_of(by_reference)) == link_sources(sink_of(by_subscript))
    assert "unresolved_ref" not in sink_of(by_reference)._metadata.extras


def test_reference_value_flows_at_run_time():
    """The referenced value reaches the task that consumes it."""

    @task.graph(outputs=ns(out=Any))
    def ByReference(codes: Codes):
        out = run_code(code=codes.reference("ph"))
        return {"out": out.result}

    graph = ByReference.build(codes={"pw": "PW", "ph": "PH"})
    assert LocalEngine().run(graph)["out"] == "ran PH"


def test_absent_member_leaves_a_required_socket_unfilled():
    """An absent member leaves the consuming socket unfilled, so a checker can see it."""

    @task.graph()
    def ByReference(codes: Codes):
        run_code(code=codes.reference("ph"))

    graph = ByReference.build(codes={"pw": "PW"})
    sink = sink_of(graph)
    assert sink._links == []
    assert sink.value is None
    assert sink._metadata.required is True
    assert sink._metadata.extras["unresolved_ref"] == "graph_inputs.codes.ph"


def test_absent_member_leaves_an_optional_socket_unset():
    """An absent member wired into an optional socket is not an error."""

    @task.graph()
    def ByReference(codes: Codes):
        maybe_run_code(code=codes.reference("ph"))

    graph = ByReference.build(codes={"pw": "PW"})
    sink = sink_of(graph, "maybe_run_code")
    assert sink._links == []
    assert sink._metadata.required is False
    assert sink._metadata.extras["unresolved_ref"] == "graph_inputs.codes.ph"


def test_required_namespace_reaches_the_body_when_empty():
    """A required namespace is passed to the body even with no member provided."""

    @task.graph()
    def ByReference(codes: Codes):
        run_code(code=codes.reference("pw"))

    graph = ByReference.build(codes={})
    assert sink_of(graph)._metadata.extras["unresolved_ref"] == "graph_inputs.codes.pw"


def test_reference_reaches_a_nested_member():
    """Dotted names reference members of nested namespaces."""

    @task.graph()
    def ByReference(config: ns(codes=ns(pw=Any))):
        run_code(code=config.reference("codes.pw"))

    provided = ByReference.build(config={"codes": {"pw": "PW"}})
    assert link_sources(sink_of(provided)) == ["graph_inputs.config.codes.pw"]

    absent = ByReference.build(config={"codes": {}})
    assert (
        sink_of(absent)._metadata.extras["unresolved_ref"]
        == "graph_inputs.config.codes.pw"
    )


def test_reference_inside_a_namespace_assignment():
    """A reference can be handed over as one member of a namespace input."""

    @task()
    def add(data: ns(x=int, y=int)) -> int:
        return data["x"] + data["y"]

    @task.graph()
    def ByReference(numbers: ns(x=int, y=NotRequired[int])):
        add(data={"x": numbers.reference("x"), "y": numbers.reference("y")})

    graph = ByReference.build(numbers={"x": 1})
    sink = graph.tasks["add"].inputs.data
    assert link_sources(sink.x) == ["graph_inputs.numbers.x"]
    assert sink.y._links == []
    assert sink.y._metadata.extras["unresolved_ref"] == "graph_inputs.numbers.y"


def test_reference_to_an_undeclared_member_raises():
    """Referencing a member the namespace does not declare fails at build."""

    @task.graph()
    def ByReference(codes: Codes):
        run_code(code=codes.reference("nope"))

    with pytest.raises(ValueError, match="not a member of namespace"):
        ByReference.build(codes={"pw": "PW"})


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
    def ByReference(codes: Codes):
        run_code(code=codes.reference("ph"))

    provided = Graph.from_dict(
        ByReference.build(codes={"pw": "PW", "ph": "PH"}).to_dict()
    )
    assert link_sources(sink_of(provided)) == ["graph_inputs.codes.ph"]

    absent = Graph.from_dict(ByReference.build(codes={"pw": "PW"}).to_dict())
    assert sink_of(absent)._links == []
    assert sink_of(absent)._metadata.extras["unresolved_ref"] == "graph_inputs.codes.ph"


# ------------------------------------------------------- free-function form
# ``reference(namespace, name)`` is the typed sibling of the
# ``namespace.reference(name)`` method: a plain function, so a body typed on
# a TypedDict (a Mapping, with no ``.reference`` method in its type) can call
# it without widening the parameter type or adding a cast. The two forms
# share behaviour; parametrize the scenarios that already cover the method
# rather than duplicating them.

REFERENCE_ACCESSORS = {
    "method": lambda namespace, name: namespace.reference(name),
    "function": lambda namespace, name: reference(namespace, name),
}


@pytest.mark.parametrize(
    "accessor", REFERENCE_ACCESSORS.values(), ids=REFERENCE_ACCESSORS.keys()
)
def test_reference_accessor_links_a_provided_member(accessor):
    """Both forms link a provided member exactly the same way."""

    @task.graph()
    def ByAccessor(codes: Codes):
        run_code(code=accessor(codes, "ph"))

    graph = ByAccessor.build(codes={"pw": "PW", "ph": "PH"})
    assert link_sources(sink_of(graph)) == ["graph_inputs.codes.ph"]


@pytest.mark.parametrize(
    "accessor", REFERENCE_ACCESSORS.values(), ids=REFERENCE_ACCESSORS.keys()
)
def test_reference_accessor_does_not_raise_for_an_absent_member(accessor):
    """Both forms return a reference where subscription raises ``KeyError``."""

    @task.graph()
    def ByAccessor(codes: Codes):
        run_code(code=accessor(codes, "ph"))

    graph = ByAccessor.build(codes={"pw": "PW"})
    sink = sink_of(graph)
    assert sink._links == []
    assert sink._metadata.extras["unresolved_ref"] == "graph_inputs.codes.ph"


@pytest.mark.parametrize(
    "accessor", REFERENCE_ACCESSORS.values(), ids=REFERENCE_ACCESSORS.keys()
)
def test_reference_accessor_reaches_a_nested_member(accessor):
    """Both forms accept a dotted name to reach a nested namespace's member."""

    @task.graph()
    def ByAccessor(config: ns(codes=ns(pw=Any))):
        run_code(code=accessor(config, "codes.pw"))

    provided = ByAccessor.build(config={"codes": {"pw": "PW"}})
    assert link_sources(sink_of(provided)) == ["graph_inputs.config.codes.pw"]


@pytest.mark.parametrize(
    "accessor", REFERENCE_ACCESSORS.values(), ids=REFERENCE_ACCESSORS.keys()
)
def test_reference_accessor_to_an_undeclared_member_raises(accessor):
    """Both forms fail at build when the name isn't in the namespace's schema."""

    @task.graph()
    def ByAccessor(codes: Codes):
        run_code(code=accessor(codes, "nope"))

    with pytest.raises(ValueError, match="not a member of namespace"):
        ByAccessor.build(codes={"pw": "PW"})


def test_reference_function_on_a_plain_dict_raises_typeerror():
    """A plain dict built by hand carries no socket identity, so ``reference()``
    names the type it received instead of failing with an unrelated
    ``AttributeError``."""
    with pytest.raises(TypeError, match=r"dict carries no socket identity"):
        reference({"pw": "PW"}, "pw")


def test_reference_typing_snippet_has_no_ignore_comments():
    """``tests/typing_check_reference.py`` is the reason ``reference()`` exists: a
    TypedDict-typed call site checked clean under mypy strict mode, with no
    escape hatch needed (verified out of band; see the PR body for the
    invocation and result — the repo has no mypy step to hook a subprocess
    check into). This test only guards the snippet against regaining one.
    """
    import pathlib

    snippet = pathlib.Path(__file__).parent / "typing_check_reference.py"
    assert "type: ignore" not in snippet.read_text()


# ------------------------------------------------ omitted-argument contract
# A required namespace that ``build()`` never received at all (as opposed to
# one explicitly assigned ``{}``) must still fail the way a plain Python call
# with a missing required argument does: `func(**inputs)` never sees it, so
# the caller gets ``TypeError``, not a graph whose body silently ran with an
# empty namespace.


def test_omitted_namespace_raises_typeerror_mixed_shape():
    """A namespace mixing a required and an optional member, entirely omitted."""

    @task.graph()
    def WithCodes(codes: Codes):
        run_code(code=codes.reference("pw"))

    with pytest.raises(
        TypeError, match=r"missing 1 required positional argument: 'codes'"
    ):
        WithCodes.build()


def test_omitted_namespace_raises_typeerror_all_optional_shape():
    """A required namespace whose every member is optional, entirely omitted.

    The namespace itself is still a required argument even though nothing
    inside it is.
    """

    @task.graph()
    def WithOptions(options: Options):
        run_code(code=options.reference("ph"))

    with pytest.raises(
        TypeError, match=r"missing 1 required positional argument: 'options'"
    ):
        WithOptions.build()


def test_explicitly_empty_namespace_still_reaches_the_body():
    """Control: `codes={}` (as opposed to omitting `codes`) still builds.

    This is the case `test_required_namespace_reaches_the_body_when_empty`
    already covers end to end; repeated here next to the omitted-argument
    tests so the two contracts are read together.
    """

    @task.graph()
    def WithCodes(codes: Codes):
        run_code(code=codes.reference("pw"))

    graph = WithCodes.build(codes={})
    assert sink_of(graph)._metadata.extras["unresolved_ref"] == "graph_inputs.codes.pw"


# --------------------------------------------- concrete NotRequired members
# node-graph#165 fixed a NotRequired[<concrete type>] TypedDict member: the
# qualifier used to survive get_type_hints and leak into the child spec as
# an opaque "annotated" leaf (identifier node_graph.annotated, required=True)
# instead of being stripped down to the wrapped type. Every other case in
# this file uses NotRequired[Any], which the pre-#165 code path already
# handled correctly and so doesn't exercise the fix.


class TypedCodes(TypedDict):
    pw: str
    ph: NotRequired[str]


@task()
def run_str(code: str) -> str:
    return f"ran {code}"


def test_reference_wires_a_concrete_typed_notrequired_member():
    """A NotRequired member with a concrete type links through `reference()`
    exactly as an `Any`-typed one does: present, it links; absent, it leaves
    the sink unresolved rather than being mis-specified as an opaque,
    always-required leaf."""

    @task.graph()
    def ByReference(codes: TypedCodes):
        run_str(code=codes.reference("ph"))

    provided = ByReference.build(codes={"pw": "PW", "ph": "PH"})
    assert link_sources(sink_of(provided, "run_str")) == ["graph_inputs.codes.ph"]

    absent = ByReference.build(codes={"pw": "PW"})
    sink = sink_of(absent, "run_str")
    assert sink._links == []
    assert sink._metadata.extras["unresolved_ref"] == "graph_inputs.codes.ph"


@task.graph()
def NestedConfig(config: ns(codes=ns(pw=Any))):
    # Graph bodies run against a re-imported function object; only a
    # module-level body reliably shares SEEN with the test that built it
    # (a locally-nested body does not, see test_reference_inside_a_namespace_assignment
    # and friends, which read the built graph's structure instead).
    SEEN["contains_codes"] = "codes" in config
    SEEN["config"] = dict(config)


def test_nested_namespace_not_kept_when_never_assigned():
    """A nested required namespace that was never itself assigned does not
    survive collection just because its parent was explicitly assigned `{}`.

    This is the same keep_empty duplication in a different shape: a
    required-based keep_empty rule (rather than one keyed on whether the
    namespace was itself explicitly assigned) would keep the nested
    namespace alive as an empty TaggedNamespace, silently flipping
    `"codes" in config` from False to True with no assignment to `codes`
    anywhere.
    """
    SEEN.clear()
    NestedConfig.build(config={})
    assert SEEN["contains_codes"] is False
    assert SEEN["config"] == {}


# ------------------------------------------------- stored-reference errors
# A SocketReference is only ever meant to be assigned directly to a socket
# (leaf or namespace), where `_set_socket_reference` decides whether to link
# it. Buried inside a plain dict/list bound for a leaf socket, nothing
# decomposes the container, so the reference would otherwise be stored as a
# bare, dead object instead of being linked or reported as unresolved.


@task()
def show(opts: Any) -> str:
    return f"opts={opts!r}"


def test_reference_nested_in_a_dict_bound_for_a_leaf_raises():
    @task.graph()
    def ReferenceInDict(codes: Codes):
        show(opts={"a": codes.reference("ph")})

    with pytest.raises(TypeError, match="would store a SocketReference"):
        ReferenceInDict.build(codes={"pw": "PW", "ph": "PH"})


def test_reference_nested_in_a_dict_bound_for_a_leaf_raises_even_when_absent():
    """The container itself can't be linked either way, so absence doesn't help."""

    @task.graph()
    def ReferenceInDict(codes: Codes):
        show(opts={"a": codes.reference("ph")})

    with pytest.raises(TypeError, match="would store a SocketReference"):
        ReferenceInDict.build(codes={"pw": "PW"})


def test_reference_nested_in_a_list_bound_for_a_leaf_raises():
    @task.graph()
    def ReferenceInList(codes: Codes):
        show(opts=["a", codes.reference("ph")])

    with pytest.raises(TypeError, match="would store a SocketReference"):
        ReferenceInList.build(codes={"pw": "PW", "ph": "PH"})


def test_reference_error_names_the_target_and_source_sockets():
    @task.graph()
    def ReferenceInDict(codes: Codes):
        show(opts={"a": codes.reference("ph")})

    with pytest.raises(TypeError) as exc:
        ReferenceInDict.build(codes={"pw": "PW", "ph": "PH"})
    assert "show.opts" in str(exc.value)
    assert "graph_inputs.codes.ph" in str(exc.value)


def test_reference_in_a_dict_bound_for_a_leaf_negative_control(monkeypatch):
    """Disabling the check reproduces the pre-fix silent-garbage behaviour.

    This is the discriminating half of the fix: without the guard, the same
    graph builds and stores the bare SocketReference as an inert value.
    """
    import node_graph.socket as socket_module

    monkeypatch.setattr(
        socket_module, "_find_nested_socket_reference", lambda value: None
    )

    @task.graph()
    def ReferenceInDict(codes: Codes):
        show(opts={"a": codes.reference("ph")})

    graph = ReferenceInDict.build(codes={"pw": "PW", "ph": "PH"})
    sink = graph.tasks["show"].inputs.opts
    assert sink._links == []
    assert isinstance(sink._value["a"], SocketReference)


def test_raw_socket_nested_in_a_leaf_dict_is_unaffected():
    """Control: a plain (non-reference) socket nested in a container still
    stores as a value today; the new check targets SocketReference only."""

    @task()
    def produce() -> str:
        return "PRODUCED"

    @task.graph()
    def NestedSocket():
        p = produce()
        show(opts={"a": p.result})

    graph = NestedSocket.build()
    sink = graph.tasks["show"].inputs.opts
    assert sink._links == []
    assert "a" in sink._value


# ------------------------------------------- unconditional socket assignment
# A reference is a distinct type because the conditional link cannot be read
# off the socket it points at. The two tests below hold the counter-examples:
# each assigns a socket that is not provided and must still link.


@task()
def produce_code() -> str:
    return "PRODUCED"


def test_a_graph_input_socket_assigned_directly_always_links():
    """``ng.inputs.<name>`` wired into a task links before it holds a value.

    This is the context-manager paradigm: inputs are declared in the spec,
    wired into tasks while empty, and supplied at run time. The socket's
    owning task is ``graph_inputs`` and it is not provided, so neither task
    identity nor provided-ness can select the conditional branch.
    """
    ng = Graph(name="context-manager-style", inputs=ns(code=Any))
    assert socket_is_provided(ng.inputs.code) is False
    assert ng.inputs.code._task.identifier == "graph_inputs"

    consumer = ng.add_task(run_code, name="run_code", code=ng.inputs.code)

    assert link_sources(consumer.inputs.code) == ["graph_inputs.code"]
    assert "unresolved_ref" not in consumer.inputs.code._metadata.extras


def test_a_task_output_socket_links_before_its_task_runs():
    """A producer's output wired into a consumer links while still empty.

    An output socket holds neither value nor link until something consumes
    it, so a branch keyed on provided-ness would turn ordinary deferred
    wiring into a silent no-op.
    """
    ng = Graph(name="deferred-wiring")
    producer = ng.add_task(produce_code, name="produce_code")
    assert socket_is_provided(producer.outputs.result) is False

    consumer = ng.add_task(run_code, name="run_code", code=producer.outputs.result)

    assert link_sources(consumer.inputs.code) == ["produce_code.result"]
    assert "unresolved_ref" not in consumer.inputs.code._metadata.extras


# --------------------------------------------- TaggedNamespace copy/pickle
# TaggedNamespace carries a live socket handle, which is neither deep-copyable
# nor picklable. copy/deepcopy/pickle fall back to a plain dict, matching
# what a caller gets from `dict(codes)`.


def test_tagged_namespace_deepcopy_yields_a_plain_dict():
    import copy

    tn = TaggedNamespace({"pw": "PW"}, socket=object())
    copied = copy.deepcopy(tn)
    assert type(copied) is dict
    assert copied == {"pw": "PW"}


def test_tagged_namespace_pickle_yields_a_plain_dict():
    import pickle

    tn = TaggedNamespace({"pw": "PW"}, socket=object())
    restored = pickle.loads(pickle.dumps(tn))
    assert type(restored) is dict
    assert restored == {"pw": "PW"}


def test_tagged_namespace_copy_module_yields_a_plain_dict():
    import copy

    tn = TaggedNamespace({"pw": "PW"}, socket=object())
    shallow = copy.copy(tn)
    assert type(shallow) is dict
    assert shallow == {"pw": "PW"}


def test_tagged_namespace_copy_method_keeps_the_socket():
    """The dict-style `.copy()` method is unaffected: it is how the framework
    itself clones a namespace value while keeping its socket handle."""
    marker = object()
    tn = TaggedNamespace({"pw": "PW"}, socket=marker)
    copied = tn.copy()
    assert type(copied) is TaggedNamespace
    assert copied._socket is marker
