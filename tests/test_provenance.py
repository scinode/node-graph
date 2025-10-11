from node_graph.engine.provenance import ProvenanceRecorder, content_hash


def test_provenance_recorder_flattens_payloads():
    recorder = ProvenanceRecorder("wf")
    pid = recorder.process_start(
        task_name="task",
        callable_obj=lambda x: x,
        flow_run_id="flow-1",
        task_run_id="task-1",
    )

    recorder.record_inputs_payload(pid, {"nested": {"inner": 42}, "x": 7})
    recorder.record_outputs_payload(pid, {"result": 13, "nested": {"value": 99}})
    recorder.process_end(pid, state="FINISHED")

    data = recorder.to_json()
    assert data["process_nodes"][pid]["state"] == "FINISHED"

    edges = {(edge["src"], edge["dst"], edge["label"]) for edge in data["edges"]}
    assert (
        f"data:{content_hash(42)}",
        pid,
        "input:nested.inner",
    ) in edges
    assert (
        pid,
        f"data:{content_hash(99)}",
        "output:nested.value",
    ) in edges


def test_provenance_recorder_save_graphviz(tmp_path):
    recorder = ProvenanceRecorder("wf-graphviz")
    pid = recorder.process_start(
        task_name="task",
        callable_obj=lambda x: x,
        flow_run_id="flow-graphviz",
        task_run_id="task-graphviz",
    )

    recorder.record_inputs_payload(pid, {"x": 1})
    recorder.record_outputs_payload(pid, {"result": 2})
    recorder.process_end(pid, state="FINISHED")

    dot_path = tmp_path / "prov.dot"
    returned = recorder.save_graphviz(str(dot_path))

    assert dot_path.exists()
    assert returned == str(dot_path)
    content = dot_path.read_text()
    assert "digraph provenance" in content
    assert '"proc:task:1"' in content
