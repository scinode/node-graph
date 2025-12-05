from typing import Any, Annotated

from node_graph import task, namespace
from node_graph import dynamic
from node_graph.semantics import (
    TaskSemantics,
    OntologyEnum,
    SemanticsAnnotation,
    SemanticsPayload,
    SemanticsRelation,
    SemanticsTree,
    SemanticTag,
    namespace_registry,
    serialize_semantics_buffer,
    _capture_semantics_value,
    _normalize_semantics_buffer,
    _socket_ref_from_value,
    attach_semantics,
)
from node_graph.socket_spec import meta


@task()
def emit(value):
    return value


@task.graph()
def simple_graph() -> Annotated[dict, namespace(first=Any, second=Any)]:
    first = emit(value=1).result
    second = emit(value=2).result
    return {"first": first, "second": second}


def test_attach_semantics_records_relations():
    graph = simple_graph.build()
    target = graph.tasks["emit"].outputs.result
    source = graph.tasks["emit1"].outputs.result

    attach_semantics(
        target,
        objects=source,
        predicate="mat:hasProperty",
        label="Relation label",
        context={"mat": "https://example.org/mat#"},
    )

    buffer = graph.semantics_buffer
    assert len(buffer["relations"]) == 1
    rel = buffer["relations"][0]
    assert isinstance(rel, SemanticsRelation)
    assert rel.predicate == "mat:hasProperty"
    assert rel.label == "Relation label"
    assert rel.subject.task_name == "emit"
    assert rel.values[0].task_name == "emit1"
    assert rel.subject.graph_uuid == graph.uuid
    assert rel.values[0].graph_uuid == graph.uuid


def test_attach_relation_helper_orders_args():
    graph = simple_graph.build()
    target = graph.tasks["emit"].outputs.result
    source = graph.tasks["emit1"].outputs.result

    attach_semantics(
        target,
        objects=source,
        predicate="emmo:hasProperty",
        label="Relation label",
        context={"emmo": "https://emmo.info/emmo#"},
    )

    buffer = graph.semantics_buffer
    assert len(buffer["relations"]) == 1
    rel = buffer["relations"][0]
    assert isinstance(rel, SemanticsRelation)
    assert rel.predicate == "emmo:hasProperty"
    assert rel.subject == _socket_ref_from_value(target)


def test_attach_semantics_with_predicate_kw():
    graph = simple_graph.build()
    target = graph.tasks["emit"].outputs.result
    source = graph.tasks["emit1"].outputs.result

    attach_semantics(
        target,
        objects=source,
        predicate="emmo:hasProperty",
        label="Relation label",
        context={"emmo": "https://emmo.info/emmo#"},
    )

    buffer = graph.semantics_buffer
    assert len(buffer["relations"]) == 1
    rel = buffer["relations"][0]
    assert isinstance(rel, SemanticsRelation)
    assert rel.predicate == "emmo:hasProperty"


def test_attach_annotation_helper_adds_payload():
    graph = simple_graph.build()
    subject = graph.tasks["emit"].outputs.result

    attach_semantics(
        subject,
        semantics={"label": "Generated structure", "iri": "emmo:Material"},
        socket_label="result",
    )

    buffer = graph.semantics_buffer
    assert len(buffer["payloads"]) == 1
    payload = buffer["payloads"][0]
    assert isinstance(payload, SemanticsPayload)
    assert payload.socket_label == "result"
    assert payload.semantics["label"] == "Generated structure"


def test_attach_semantics_records_payloads():
    graph = simple_graph.build()
    subject = graph.tasks["emit"].outputs.result

    attach_semantics(subject, semantics={"label": "Sample", "iri": "qudt:Energy"})

    buffer = graph.semantics_buffer
    assert len(buffer["payloads"]) == 1
    payload = buffer["payloads"][0]
    assert isinstance(payload, SemanticsPayload)
    assert payload.socket_label is None
    assert payload.semantics["label"] == "Sample"
    assert payload.semantics["iri"] == "qudt:Energy"
    assert payload.subject.task_name == "emit"
    assert payload.subject.graph_uuid == graph.uuid


def test_attach_semantics_with_predicate_and_annotation_payload():
    graph = simple_graph.build()
    target = graph.tasks["emit"].outputs.result
    source = graph.tasks["emit1"].outputs.result

    attach_semantics(
        target,
        objects=source,
        predicate="emmo:hasProperty",
        semantics={"iri": "emmo:Material"},
        label="Material annotation",
        context={"emmo": "https://emmo.info/emmo#"},
        socket_label="result",
    )

    buffer = graph.semantics_buffer
    assert buffer["relations"] == []
    assert len(buffer["payloads"]) == 1
    payload = buffer["payloads"][0]
    assert isinstance(payload, SemanticsPayload)
    assert payload.socket_label == "result"
    assert payload.subject == _socket_ref_from_value(target)
    semantics = payload.semantics
    assert isinstance(semantics, dict)
    assert semantics["iri"] == "emmo:Material"
    assert semantics["label"] == "Material annotation"
    assert semantics["context"]["emmo"] == "https://emmo.info/emmo#"
    assert semantics["relations"]["emmo:hasProperty"] == _socket_ref_from_value(source)


def test_serialization_roundtrip_preserves_semantics_buffer():
    graph = simple_graph.build()
    subject = graph.tasks["emit"].outputs.result
    attach_semantics(subject, semantics={"label": "Sample"})

    serialized = graph.to_dict()
    rebuilt = type(graph).from_dict(serialized)

    assert (
        serialize_semantics_buffer(rebuilt.semantics_buffer)
        == serialized["semantics_buffer"]
    )


def test_semantics_annotation_merge_and_combine():
    a = SemanticsAnnotation(label="A", rdf_types=("x",))
    b = SemanticsAnnotation(iri="iri", rdf_types=("x", "y"), attributes={"k": 1})
    merged = a.merge(b)
    assert merged.label == "A"
    assert merged.iri == "iri"
    assert merged.rdf_types == ("x", "y")
    assert merged.attributes["k"] == 1

    combined = SemanticsAnnotation.combine([None, a, SemanticsAnnotation(), b])
    assert combined == merged


def test_semantics_tree_resolves_paths_with_dynamic_namespace():
    spec = namespace(
        fixed=Annotated[Any, meta(semantics={"label": "Fixed"})],
        dynamic=dynamic(Annotated[Any, meta(semantics={"label": "Dyn"})]),
    )
    tree = SemanticsTree.from_spec(spec)
    assert tree.children["fixed"].annotation.label == "Fixed"
    assert tree.children["dynamic"].dynamic.annotation.label == "Dyn"


def test_socket_ref_capture_and_normalize():
    graph = simple_graph.build()
    target_socket = graph.tasks["emit"].outputs.result
    captured = _capture_semantics_value({"s": target_socket, "list": [target_socket]})
    ref = captured["s"]
    assert _socket_ref_from_value(target_socket) == ref
    normalized = _normalize_semantics_buffer(
        {
            "relations": [
                {
                    "predicate": "p",
                    "subject": ref.__dict__,
                    "values": (ref.__dict__,),
                }
            ],
            "payloads": [
                {
                    "subject": ref.__dict__,
                    "semantics": {"label": "L"},
                    "socket_label": "result",
                }
            ],
        }
    )
    assert isinstance(normalized["relations"][0], SemanticsRelation)
    assert isinstance(normalized["payloads"][0], SemanticsPayload)


def test_task_semantics_from_specs_and_dict():
    inputs = namespace(
        x=Annotated[Any, meta(semantics={"label": "X"})],
    )
    outputs = namespace(result=Annotated[Any, meta(semantics={"label": "R"})])
    spec_semantics = TaskSemantics.from_specs(inputs, outputs)
    assert spec_semantics.resolve_input("x").label == "X"
    assert spec_semantics.resolve_output("result").label == "R"

    back = TaskSemantics.from_dict(spec_semantics.to_dict())
    assert back.resolve_output("result").label == "R"


def test_semantics_annotation_to_jsonld():
    ann = SemanticsAnnotation(
        label="Energy",
        iri="qudt:Energy",
        rdf_types=("qudt:QuantityValue",),
        context={"qudt": "http://qudt.org/schema/qudt/"},
        attributes={"qudt:unit": "qudt-unit:EV"},
        relations={"schema:isDefinedBy": {"@id": "http://example.org/def"}},
    )
    payload = ann.to_jsonld()
    assert payload["@id"] == "qudt:Energy"
    assert payload["@type"] == ["qudt:QuantityValue"]
    assert payload["@context"]["qudt"].endswith("qudt/")
    assert payload["qudt:unit"] == "qudt-unit:EV"
    assert payload["schema:isDefinedBy"]["@id"] == "http://example.org/def"


def test_semantic_tag_autofills_context_and_attributes():
    class EnergyTerms(OntologyEnum):
        PotentialEnergy = "qudt:PotentialEnergy"
        QuantityValue = "qudt:QuantityValue"

    tag = SemanticTag(
        label="Cohesive energy",
        iri=EnergyTerms.PotentialEnergy,
        rdf_types=(EnergyTerms.QuantityValue,),
        attributes={"qudt:unit": "qudt-unit:EV"},
    )
    annotation = SemanticsAnnotation.from_raw(tag)
    assert annotation is not None
    assert annotation.iri == "qudt:PotentialEnergy"
    assert annotation.attributes["qudt:unit"] == "qudt-unit:EV"
    assert "qudt" in annotation.context and "qudt-unit" in annotation.context


def test_default_namespace_registry_injects_missing_context():
    ann = SemanticsAnnotation.from_raw({"iri": "prov:Entity"})
    assert ann is not None
    registry = namespace_registry()
    assert all(prefix in registry for prefix in ("prov", "schema", "qudt"))
    assert ann.context["prov"] == registry["prov"]
