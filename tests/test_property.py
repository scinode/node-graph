import pytest
from node_graph import NodeGraph
from node_graph.property import NodeProperty
from node_graph.node import Node


@pytest.mark.parametrize(
    "id, data",
    (
        ("node_graph.int", 1),
        ("node_graph.float", 1.0),
        ("node_graph.bool", False),
        ("node_graph.string", "a"),
        ("node_graph.base_dict", {"a": 1}),
        ("node_graph.base_list", [1, 2, 3]),
    ),
)
def test_base_type(id, data):
    """Test base type property."""

    p = NodeProperty.new(id)
    p.value = data
    assert p.value == data
    # copy
    p1 = p.copy()
    assert p1.value == data


@pytest.mark.parametrize(
    "id, data",
    (
        ("node_graph.int", "a"),
        ("node_graph.float", "a"),
        ("node_graph.bool", "a"),
        ("node_graph.string", 0.0),
        ("node_graph.base_dict", 0.0),
        ("node_graph.base_list", 0.0),
    ),
)
def test_base_type_validation(id, data):
    """Test base type validation."""

    p = NodeProperty.new(id)
    try:
        p.value = data
    except Exception as e:
        assert e is not None
    assert p.value != data


def test_enum_type():
    """Test simple math."""

    ng = NodeGraph(name="test_enum_type")
    nd = ng.add_node("node_graph.test_enum")
    assert nd.properties["function"].content == "test_add"
    nd.properties["function"].value = "sqrt"
    assert nd.properties["function"].content == "test_sqrt"


def test_enum_update_type():
    """Test simple math."""

    ng = NodeGraph(name="test_enum_update_type")
    nd = ng.add_node("node_graph.test_enum_update")
    assert nd.properties["function"].content == "test_add"
    assert len(nd.inputs) == 2
    nd.properties["function"].value = "sqrt"
    assert len(nd.inputs) == 1
    pdata = nd.export_properties()
    assert pdata["function"]["value"] == "sqrt"
    # copy
    p1 = nd.properties["function"].copy()
    assert p1.value == "sqrt"


@pytest.mark.parametrize(
    "id, size, default, data",
    (
        ("node_graph.int_vector", 3, [0, 0, 0], [1, 2, 3]),
        ("node_graph.float_vector", 3, [0.0, 0.0, 0.0], [1.0, 2.0, 3.0]),
        ("node_graph.bool_vector", 3, [True, True, True], [False, True, False]),
    ),
)
def test_vector(id, size, default, data):
    """Test simple math."""

    ng = NodeGraph(name="test_vector")
    nd = ng.add_node(Node)
    nd.executor = {"module_path": "numpy.sqrt"}
    nd.args = ["x"]
    nd.add_property(id, "x", **{"size": size, "default": default})
    nd.properties[0].value = data
    assert nd.properties[0].value == data
    # copy
    p1 = nd.properties[0].copy()
    assert p1.value == data


@pytest.mark.parametrize(
    "id, size, default, data",
    (("node_graph.float_matrix", [2, 2], [0.0, 0.0, 0.0, 0.0], [1.0, 2.0, 3.0, 4.0]),),
)
def test_matrix(id, size, default, data):
    ng = NodeGraph(name="test_vector")
    nd = ng.add_node(Node)
    nd.executor = {"module_path": "numpy.sqrt"}
    nd.args = ["x"]
    nd.add_property(id, "x", **{"size": size, "default": default})
    nd.properties[0].value = data
    assert nd.properties[0].value == data
    # copy
    p1 = nd.properties[0].copy()
    assert p1.value == data


def test_repr():
    """Test __repr__ method."""
    ng = NodeGraph(name="test_repr")
    node = ng.add_node("node_graph.test_enum", "node1")
    assert (
        repr(node.properties)
        == 'PropertyCollection(node = "node1", properties = ["t", "function"])'
    )
