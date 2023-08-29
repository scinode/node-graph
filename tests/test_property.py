import pytest
from node_graph import NodeGraph


@pytest.mark.parametrize(
    "id, data",
    (
        ("Int", 1),
        ("Float", 1.0),
        ("Bool", False),
        ("String", "a"),
        ("BaseDict", {"a": 1}),
        ("BaseList", [1, 2, 3]),
    ),
)
def test_base_type(id, data):
    """Test base type property."""
    from node_graph.property import NodeProperty

    p = NodeProperty.new(id)
    p.value = data
    assert p.value == data
    # copy
    p1 = p.copy()
    assert p1.value == data


@pytest.mark.parametrize(
    "id, data",
    (
        ("Int", "a"),
        ("Float", "a"),
        ("Bool", "a"),
        ("String", 0.0),
        ("BaseDict", 0.0),
        ("BaseList", 0.0),
    ),
)
def test_base_type_validation(id, data):
    """Test base type validation."""
    from node_graph.property import NodeProperty

    p = NodeProperty.new(id)
    try:
        p.value = data
    except Exception as e:
        assert e is not None
    assert p.value != data


def test_enum_type():
    """Test simple math."""

    nt = NodeGraph(name="test_enum_type")
    nd = nt.nodes.new("TestEnum")
    assert nd.properties["function"].content == "test_add"
    nd.properties["function"].value = "sqrt"
    assert nd.properties["function"].content == "test_sqrt"


def test_enum_update_type():
    """Test simple math."""

    nt = NodeGraph(name="test_enum_update_type")
    nd = nt.nodes.new("TestEnumUpdate")
    assert nd.properties["function"].content == "test_add"
    assert len(nd.inputs) == 2
    nd.properties["function"].value = "sqrt"
    assert len(nd.inputs) == 1
    pdata = nd.properties_to_dict()
    assert pdata["function"]["value"] == "sqrt"
    # copy
    p1 = nd.properties["function"].copy()
    assert p1.value == "sqrt"


@pytest.mark.parametrize(
    "id, size, default, data",
    (
        ("IntVector", 3, [0, 0, 0], [1, 2, 3]),
        ("FloatVector", 3, [0.0, 0.0, 0.0], [1.0, 2.0, 3.0]),
        ("BoolVector", 3, [True, True, True], [False, True, False]),
    ),
)
def test_vector(id, size, default, data):
    """Test simple math."""
    from node_graph.node import Node

    nt = NodeGraph(name="test_vector")
    nd = nt.nodes.new(Node)
    nd.executor = {"path": "numpy.sqrt"}
    nd.args = ["x"]
    nd.properties.new(id, "x", **{"size": size, "default": default})
    nd.properties[0].value = data
    print(nd.properties[0].value)
    assert nd.properties[0].value == data
    # copy
    p1 = nd.properties[0].copy()
    assert p1.value == data
