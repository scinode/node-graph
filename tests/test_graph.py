from node_graph import Graph, task, namespace
from node_graph.config import INPUT_SOCKET_NAME, OUTPUT_SOCKET_NAME
from node_graph.graph import GraphMetadata
from pydantic import ConfigDict
import pytest
from typing import Any
from node_graph.tasks.tests import test_float, test_add


@pytest.fixture
def test_ng():
    """A test node_graph."""

    @task(
        inputs=namespace(
            input1=namespace(x=Any, y=Any), input2=namespace(x=Any, y=Any)
        ),
        outputs=namespace(
            output1=namespace(x=Any, y=Any), output2=namespace(x=Any, y=Any)
        ),
    )
    def add():
        pass

    ng = Graph(name="test_graph")
    ng.add_task(add, "add1")
    ng.add_task(add, "add2")
    ng.add_task(add, "add3")
    return ng


def test_from_dict(ng_decorator):
    """Export Graph to dict."""
    ng = ng_decorator
    ntdata = ng_decorator.to_dict()
    ng1 = Graph.from_dict(ntdata)
    assert len(ng.tasks) == len(ng1.tasks)
    assert len(ng.links) == len(ng1.links)
    assert ng.to_dict() == ng1.to_dict()


def test_from_dict_discards_stale_graph_type():
    """A stored graph_type key from an old payload loads without error."""
    ng = Graph(name="test_graph")
    ngdata = ng.to_dict()
    assert "graph_type" not in ngdata["metadata"]
    ngdata["metadata"]["graph_type"] = "NORMAL"
    restored = Graph.from_dict(ngdata)
    assert not hasattr(restored, "graph_type")
    assert "graph_type" not in restored.to_dict()["metadata"]


def test_from_dict_namespace_links():
    @task()
    def make_pair(x: int, y: int) -> namespace(a=int, nested=namespace(x=int, y=int)):
        return {"a": x, "nested": {"x": x, "y": y}}

    @task()
    def consume(a: int, nested: namespace(x=int, y=int)) -> int:
        return a + nested["x"] + nested["y"]

    ng = Graph()
    ng.add_task(make_pair, "make_pair")
    ng.add_task(consume, "consume")
    ng.add_link(ng.tasks.make_pair.outputs, ng.tasks.consume.inputs)

    payload = ng.to_dict()
    ns_link = next(
        link
        for link in payload["links"]
        if link["from_task"] == "make_pair"
        and link["to_task"] == "consume"
        and link["to_socket"] == INPUT_SOCKET_NAME
    )
    assert ns_link["from_socket"] == OUTPUT_SOCKET_NAME

    restored = Graph.from_dict(payload)

    assert len(restored.links) == len(ng.links)
    assert any(
        link.from_socket is restored.tasks.make_pair.outputs["_outputs"]
        and link.to_socket is restored.tasks.consume.inputs
        for link in restored.links
    )
    assert any(
        link.from_socket is restored.tasks.make_pair.outputs.nested.x
        for link in restored.tasks.consume.inputs.nested.x._links
    )
    assert any(
        link.from_socket is restored.tasks.make_pair.outputs.nested.y
        for link in restored.tasks.consume.inputs.nested.y._links
    )


def test_new_node(ng):
    """Test new task."""
    ng = Graph(name="test_graph")
    n1 = ng.add_task(test_add)
    n2 = ng.add_task(test_add)
    assert n1.name == "test_add"
    assert n2.name == "test_add1"
    assert len(ng.tasks) == 5
    # add builtin task is not allowed
    name = "graph_inputs"
    with pytest.raises(
        ValueError,
        match=f"Name {name} can not be used, it is reserved.",
    ):
        ng.add_task(test_add, name=name)


def test_set_inputs(decorated_myadd):
    ng = Graph(
        name="test_graph",
        inputs=namespace(x=Any, y=Any),
        outputs=namespace(result=Any),
    )
    n1 = ng.add_task(decorated_myadd, x=ng.inputs.x, name="add1")
    n2 = ng.add_task(decorated_myadd, x=ng.inputs.y, y=n1.outputs.result, name="add2")
    ng.outputs.result = n2.outputs.result
    ng.set_inputs({"graph_inputs": {"x": 1, "y": 2}, "add1": {"y": 2}})
    assert ng.inputs.x.value == 1
    assert ng.inputs.y.value == 2
    assert ng.tasks["add1"].inputs.y.value == 2


def test_delete_node(ng):
    """Test delete task."""
    n = len(ng.tasks)
    nlink = len(ng.links)
    ng.add_task(test_add, name="add3")
    ng.add_link(ng.tasks["add1"].outputs[0], ng.tasks["add3"].inputs["y"])
    assert len(ng.tasks) == n + 1
    assert len(ng.links) == nlink + 1
    ng.delete_tasks(["add3"])
    assert len(ng.tasks) == n
    assert len(ng.links) == nlink


def test_copy(ng):
    """Test copy task graph"""
    n = len(ng.tasks)
    nlink = len(ng.links)
    ng1 = ng.copy()
    assert len(ng1.tasks) == n
    assert len(ng1.links) == nlink


def test_add_another_graph(ng):
    """Test add another graph."""
    n = len(ng.tasks)
    nlink = len(ng.links)
    ng1 = Graph(name="test_add")
    ng1.add_task(test_float, "float3", value=4.0, t=3)
    ng1.add_task(test_float, "float4", value=3.0)
    ng = ng + ng1
    assert len(ng.tasks) == n + 2
    assert len(ng.links) == nlink


def test_copy_subset(ng):
    """Test copy subset of tasks."""
    ng1 = ng.copy_subset(["add1", "add2"])
    assert len(ng1.tasks) == 6
    assert len(ng1.links) == 2
    assert "float1" in ng1.get_task_names()


def test_get_items(ng):
    """Test get items."""
    ng1 = ng[["add1", "add2"]]
    assert len(ng1.tasks) == 6
    assert len(ng1.links) == 2
    assert "float1" in ng1.get_task_names()


def test_load_graph():
    @task(
        outputs=namespace(sum=Any, product=Any, nested=namespace(sum=Any, product=Any)),
    )
    def test(a, b=1, nested: namespace(d=Any, f=namespace(g=Any, h=Any)) = {}):
        return {
            "sum": a + b,
            "product": a * b,
            "nested": {"sum": a + b, "product": a * b},
        }

    ng = Graph()
    test1 = ng.add_task(test, "test1")
    test1.set_inputs(
        {
            "a": 1,
            "b": 2,
            "nested": {"d": 2, "f": {"g": 1, "h": 2}},
        }
    )
    ngdata = ng.to_dict()
    # load graph
    ng1 = Graph.from_dict(ngdata)
    assert "sum" in ng1.tasks.test1.outputs.nested
    assert ng1.tasks.test1.inputs._value == ng.tasks.test1.inputs._value


def test_expose_inputs(test_ng):
    """Test generation of inputs from tasks"""
    ng = test_ng
    ng.expose_inputs()
    assert "add1" in ng.inputs
    assert "add1" in ng.spec.inputs.fields
    assert ng.inputs.add1._value == ng.tasks["add1"].inputs._value
    assert ng.inputs.add2._value == ng.tasks["add2"].inputs._value


def test_expose_inputs_names(test_ng):
    """Test generation of inputs from named tasks"""
    ng = test_ng
    ng.expose_inputs(names=["add1", "add2"])
    assert "add1" in ng.inputs
    assert "add2" in ng.inputs
    assert "add3" not in ng.inputs
    assert ng.inputs.add2._value == ng.tasks["add2"].inputs._value


def test_expose_inputs_names_invalid(test_ng):
    """Test that input generation fails for invalid name"""
    name = "missing"
    with pytest.raises(
        ValueError,
        match="The following tasks do not exist:",
    ):
        test_ng.expose_inputs(names=[name])


def test_expose_inputs_skip_linked(test_ng):
    """Test generation of inputs from tasks, skip linking for linked sockets"""
    ng = test_ng
    ng.add_link(ng.tasks.add1.outputs.output1.x, ng.tasks.add2.inputs.input1.x)
    ng.expose_inputs()
    assert "add2" in ng.inputs
    assert "input1.x" in ng.inputs.add2
    assert "input1.y" in ng.inputs.add2
    assert all(
        link.from_socket is not ng.inputs.add2.input1.x
        for link in ng.tasks.add2.inputs.input1.x._links
    )
    assert any(
        link.from_socket is ng.inputs.add2.input1.y
        and link.to_socket is ng.tasks.add2.inputs.input1.y
        for link in ng.tasks.add2.inputs.input1.y._links
    )
    # outputs will still have all sockets
    ng.expose_outputs()
    assert "add1" in ng.outputs
    assert "output1.x" in ng.outputs.add1
    assert "output1.y" in ng.outputs.add1


def test_expose_outputs(test_ng):
    """Test generation of outputs from tasks"""
    ng = test_ng
    ng.expose_outputs()
    assert "add1" in ng.outputs
    assert "add1" in ng.spec.outputs.fields
    assert ng.outputs.add1._value == ng.tasks["add1"].outputs._value
    assert ng.outputs.add2._value == ng.tasks["add2"].outputs._value


def test_graph_metadata_roundtrip():
    meta = {"foo": "bar", "definition": {"package_version": "1.2.3"}}
    ng = Graph(name="meta_graph", metadata=meta)
    payload = ng.to_dict()
    restored = Graph.from_dict(payload)
    assert restored._metadata["foo"] == "bar"
    assert restored.get_metadata()["foo"] == "bar"
    assert restored._metadata["definition"]["package_version"] == "1.2.3"


def test_metadata_schema_permissive_by_default():
    """Base `Graph` keeps any metadata key, unchanged from before this feature existed."""
    ng = Graph(name="permissive", metadata={"anything": "goes", "another": 1})
    assert ng._metadata == {"anything": "goes", "another": 1}
    assert ng.to_dict()["metadata"]["anything"] == "goes"


def test_metadata_declared_key_type_is_checked():
    """A declared key holding the wrong type is refused, even on permissive `Graph`."""
    with pytest.raises(ValueError, match="graph_class"):
        Graph(name="wrong-type", metadata={"graph_class": "not a dict"})


@pytest.fixture
def strict_graph():
    """A `Graph` subclass whose metadata schema adds `pk` and forbids unknown keys."""

    class StrictMetadata(GraphMetadata, total=False):
        __pydantic_config__ = ConfigDict(extra="forbid")

        pk: int

    class StrictGraph(Graph):
        _metadata_schema = StrictMetadata

    return StrictGraph


def test_subclass_narrows_metadata_schema(strict_graph):
    """A subclass declaring a wider TypedDict with `extra="forbid"` refuses a typo."""

    assert strict_graph(name="strict", metadata={"pk": 1})._metadata == {"pk": 1}
    with pytest.raises(ValueError, match="typo_key"):
        strict_graph(name="strict", metadata={"typo_key": 1})
    with pytest.raises(ValueError, match="pk"):
        strict_graph(name="strict", metadata={"pk": "not an int"})


def test_metadata_validated_at_serialization_not_at_mutation(strict_graph):
    """`_metadata` is a plain dict: a stray key survives assignment and raises at `to_dict()`."""

    ng = strict_graph(name="strict")
    ng.metadata["typo_key"] = 1  # no complaint here: no setter, no custom dict
    with pytest.raises(ValueError, match="typo_key"):
        ng.to_dict()
    del ng.metadata["typo_key"]
    ng.metadata = {"typo_key": 1}  # whole-dict reassignment behaves the same way
    with pytest.raises(ValueError, match="typo_key"):
        ng.to_dict()


def test_metadata_property_is_the_live_dict():
    """`Graph.metadata` reads and writes `_metadata` itself, with no checks of its own."""
    ng = Graph(name="plain", metadata={"start": 1})
    assert ng.metadata is ng._metadata
    ng.metadata["added"] = 2
    assert ng.to_dict()["metadata"]["added"] == 2
    ng.metadata = {"replaced": 3}
    assert ng._metadata == {"replaced": 3}
    assert "added" not in ng.to_dict()["metadata"]


def test_metadata_schema_enforced_on_from_dict(strict_graph):
    """`from_dict()` refuses a payload key the schema doesn't declare, naming graph and key."""

    payload = strict_graph(name="strict", metadata={"pk": 1}).to_dict()
    payload["metadata"]["legacy_key"] = "from an old version"
    with pytest.raises(ValueError) as excinfo:
        strict_graph.from_dict(payload)
    assert "graph 'strict'" in str(excinfo.value)
    assert "legacy_key" in str(excinfo.value)


def test_to_dict_metadata_is_the_validated_copy():
    """`to_dict()` writes exactly what `validate_metadata()` returns, not the raw dict."""
    ng = Graph(name="dumped", metadata={"definition": {"module": "m"}, "spare": 1})
    dumped = ng.to_dict()["metadata"]
    assert dumped == Graph.validate_metadata(ng.get_metadata())
    # the dump is a copy: mutating it leaves the graph's own metadata alone
    dumped["spare"] = 2
    assert ng._metadata["spare"] == 1


def test_graph_definition_metadata_from_build():
    @task.graph(outputs=namespace(result=Any))
    def test_graph(x):
        return {"result": x}

    ng = test_graph.build(1)
    assert "definition" in ng._metadata
    assert ng._metadata["definition"].get("task_identifier") == "test_graph.test_graph"


def test_expose_outputs_names(test_ng):
    """Test generation of outputs from named tasks"""
    ng = test_ng
    ng.expose_outputs(names=["add1"])
    assert ng.outputs.add1._value == ng.tasks["add1"].outputs._value
    assert "add2" not in ng.outputs


def test_expose_outputs_names_invalid(test_ng):
    """Test that output generation fails for invalid name"""
    name = "missing"
    with pytest.raises(
        ValueError,
        match="The following tasks do not exist:",
    ):
        test_ng.expose_outputs(names=[name])


def test_build_inputs_outputs(ng):
    """Test build graph inputs and outputs."""
    ng = Graph(
        name="test_graph_inputs_outputs",
        inputs=namespace(a=Any, b=Any, c=namespace(x=Any, y=Any)),
        outputs=namespace(sum=Any, product=Any, nested=namespace(sum=Any, product=Any)),
    )
    assert "a" in ng.inputs
    assert "x" in ng.inputs.c
    assert "sum" in ng.outputs
    assert "sum" in ng.outputs.nested
    assert ng.inputs._metadata.child_default_link_limit == 1000000
