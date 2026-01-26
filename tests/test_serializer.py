def test_task_to_dict_serializes_inputs():
    """Task.to_dict should use the graph serializer when requested."""
    from node_graph import Graph
    from node_graph.tasks.tests import test_add

    class DummySerializer:
        def serialize(self, value, socket, *, store: bool):
            return {"serialized": value}

    ng = Graph(name="test_serialize_inputs", serialization=DummySerializer())
    task = ng.add_task(test_add, name="add1")
    task.set_inputs({"x": 1, "y": 2})

    data = task.to_dict(should_serialize=True)
    assert data["inputs"] == {
        "x": {"serialized": 1},
        "y": {"serialized": 2},
        "t": {"serialized": 1},
    }


def test_socket_level_serialization_override():
    """Socket-level _serialize_value should override graph serialization."""
    from node_graph import Graph
    from node_graph.tasks.tests import test_add

    def _serialize_value(self, store: bool = False):
        return {"custom": self._value}

    ng = Graph(name="test_socket_serialize")
    task = ng.add_task(test_add, name="add1")
    task.set_inputs({"x": 5, "y": 7})

    task.inputs["x"].set_serializer(_serialize_value)

    data = task.to_dict(should_serialize=True)
    assert data["inputs"]["x"] == {"custom": 5}
    assert data["inputs"]["y"] == 7
