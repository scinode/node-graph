def test_task_to_dict_serializes_inputs():
    """Task.to_dict should use the graph serializer when requested."""
    from node_graph import Graph
    from node_graph.tasks.tests import test_add

    class DummySerializer:
        def serialize_ports(self, python_data, port_schema, *, store: bool):
            return {"serialized": python_data}

    ng = Graph(name="test_serialize_inputs", serialization=DummySerializer())
    task = ng.add_task(test_add, name="add1")
    task.set_inputs({"x": 1, "y": 2})

    data = task.to_dict(should_serialize=True)
    assert data["inputs"] == {"serialized": {"x": 1, "y": 2, "t": 1}}
