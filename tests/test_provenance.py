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
