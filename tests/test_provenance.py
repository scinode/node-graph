from node_graph.engine.provenance import ProvenanceRecorder
from node_graph.socket import TaggedValue


def test_provenance_recorder_flattens_payloads():
    recorder = ProvenanceRecorder("wf")
    pid = recorder.process_start(
        task_name="task",
        callable_obj=lambda x: x,
        flow_run_id="flow-1",
        task_run_id="task-1",
    )
    inputs = {"nested": {"inner": TaggedValue(42)}, "x": TaggedValue(7)}
    recorder.record_inputs_payload(
        pid,
        inputs,
    )
    outputs = {"result": TaggedValue(13), "nested": {"value": TaggedValue(99)}}
    recorder.record_outputs_payload(
        pid,
        outputs,
    )
    recorder.process_end(pid, state="FINISHED")

    data = recorder.to_json()
    assert data["process_nodes"][pid]["state"] == "FINISHED"

    edges = {(edge["src"], edge["dst"], edge["label"]) for edge in data["edges"]}
    assert (
        f"data:{inputs['nested']['inner']._uuid}",
        pid,
        "input:nested.inner",
    ) in edges
    assert (
        pid,
        f"data:{outputs['nested']['value']._uuid}",
        "output:nested.value",
    ) in edges


def test_provenance_recorder_handles_leaf_dicts():
    recorder = ProvenanceRecorder("wf-leaf")
    pid = recorder.process_start(
        task_name="leaf",
        callable_obj=lambda x: x,
        flow_run_id="flow-2",
        task_run_id="task-2",
    )

    payload = {"blob": TaggedValue({"a": 1, "b": 2})}

    recorder.record_outputs_payload(pid, payload)
    recorder.process_end(pid, state="FINISHED")

    edges = {
        (edge["src"], edge["dst"], edge["label"])
        for edge in recorder.to_json()["edges"]
    }
    assert (
        pid,
        f"data:{payload['blob']._uuid}",
        "output:blob",
    ) in edges


def test_provenance_recorder_save_graphviz(tmp_path):
    recorder = ProvenanceRecorder("wf-graphviz")
    pid = recorder.process_start(
        task_name="task",
        callable_obj=lambda x: x,
        flow_run_id="flow-graphviz",
        task_run_id="task-graphviz",
    )

    recorder.record_inputs_payload(pid, {"x": TaggedValue(1)})
    recorder.record_outputs_payload(pid, {"result": TaggedValue(2)})
    recorder.process_end(pid, state="FINISHED")

    dot_path = tmp_path / "prov.dot"
    returned = recorder.save_graphviz(str(dot_path))

    assert dot_path.exists()
    assert returned == str(dot_path)
    content = dot_path.read_text()
    assert "digraph provenance" in content
    assert '"proc:task:1"' in content
    assert 'fillcolor="#f6f6f6"' in content
