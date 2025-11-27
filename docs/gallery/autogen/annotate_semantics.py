"""
Use annotations to capture ontology semantics
=============================================

node-graph captures structural provenance out of the box, but structural links
do not explain what a piece of data *means*. Semantics add domain ontology
context—labels, IRIs, units, and relations—so every ``Data`` task carries a
machine-readable JSON-LD breadcrumb. This page introduces ontologies, shows
how node-graph stores semantics, and provides runnable examples.
"""

# %%
# Why ontologies and semantics?
# -----------------------------
# **Ontology (plain words)**: a curated dictionary of concepts and their
# relationships. Scientific ontologies describe things like “potential
# energy,” “graphene,” or “defect.” Examples:
#
# - QUDT: Quantities/Units (``qudt:PotentialEnergy``, ``qudt-unit:EV``)
# - PROV-O: Provenance concepts (``prov:Entity``, ``prov:Activity``)
# - Any in-house/discipline vocabulary.
#
# **Semantics**: tagging actual data with ontology identifiers so machines can
# tell *what* a number represents (e.g., cohesive energy vs. temperature).
#
# Benefits:
#
# - Interoperability: exports slot into ELNs/portals without glue code.
# - Queryability: predicates like ``qudt:unit`` enable rich searches.
# - Traceability: annotations document how to interpret each socket.

# %%
# Context and namespaces
# ----------------------
# Semantics payloads carry an ``@context`` map so CURIE-style identifiers such
# as ``qudt:Energy`` resolve to full IRIs. node-graph comes with a small default
# registry (``qudt``, ``qudt-unit``, ``prov``, ``schema``). When it sees those
# prefixes in ``iri`` / ``rdf_types`` / keys, it automatically injects their
# URLs into ``@context`` unless you provided a value already.
#
# - To extend the registry globally, call ``register_namespace("mat",
#   "https://example.org/mat#")`` once at import time.
# - To add a custom prefix for a single annotation, include it directly in the
#   ``context`` dictionary of ``SemanticTag`` or the raw semantics payload.
# - Explicit values always win over the defaults, so you can override or
#   refine the URL per annotation if needed.

# %%
# How node-graph stores semantics
# ------------------------------
# 1. **Authoring**: sockets declare ``meta(semantics={...})`` (label, iri,
#    rdf_types, context, attributes, relations). The graph keeps these in
#    ``Graph.semantics_buffer`` so they survive serialization.
# 2. **Execution**: engines match sockets to produced/consumed ``Data`` nodes,
#    build JSON-LD snippets, and store them under ``node.base.extras['semantics']``.
# 3. **Cross-socket references**: values inside ``relations`` or ``attributes``
#    may refer to sockets (``"outputs.result"``).
# 4. **Runtime attachments**: ``node_graph.semantics.attach_semantics`` lets you
#    declare relations inside workflow code; the graph buffer remembers them
#    until execution completes.

# %%
# Declaring socket semantics
# --------------------------
# When exchanging scientific data, it is often useful to attach ontology metadata to clarify
# what a value represents. ``meta`` accepts a dedicated ``semantics=`` payload so you do not need
# to funnel these details through ``extras``.

from typing import Annotated, Any
from node_graph import task
from node_graph.socket_spec import meta, namespace

energy_semantics_meta = meta(
    semantics={
        "label": "Potential energy",
        "iri": "qudt:PotentialEnergy",
        "rdf_types": ["qudt:QuantityValue"],
        "context": {
            "qudt": "http://qudt.org/schema/qudt/",
            "qudt-unit": "http://qudt.org/vocab/unit/",
        },
        "attributes": {
            "qudt:unit": "qudt-unit:EV",
        },
    }
)


@task()
def AnnotateSemantics(energy: float) -> Annotated[float, energy_semantics_meta]:
    return energy


# %%
# Typed semantics with Pydantic
# -----------------------------
# To reduce stringly-typed mistakes, you can supply a ``SemanticTag`` (Pydantic
# model) instead of a raw dictionary. Define your own enums to avoid typos;
# missing namespace prefixes are auto-injected when they match the registry.

from enum import Enum
from node_graph.semantics import SemanticTag


class EnergyTerms(str, Enum):
    PotentialEnergy = "qudt:PotentialEnergy"
    QuantityValue = "qudt:QuantityValue"
    ElectronVolt = "qudt-unit:EV"


EnergyEV = SemanticTag(
    label="Cohesive energy",
    iri=EnergyTerms.PotentialEnergy,
    rdf_types=(EnergyTerms.QuantityValue,),
    attributes={"qudt:unit": EnergyTerms.ElectronVolt},
)


@task()
def TypedSemantics(energy: float) -> Annotated[float, meta(semantics=EnergyEV)]:
    return energy


# %%
# Cross-socket relation example
# -----------------------------
# One can also declare relations between sockets using dotted paths to refer to sibling inputs/outputs.
# For example, the following workflow declares that the input
# ``structure`` has a relation ``mat:hasProperty`` pointing to the output of the
# ``compute_band_structure`` task.


@task()
def compute_band_structure(structure):
    return 1.0


structure_meta = meta(
    semantics={
        "label": "Crystal structure",
        "context": {"mat": "https://example.org/mat#"},
        "relations": {
            "mat:hasProperty": [
                {
                    "socket": "outputs.result",
                    "label": "Band structure property",
                    "context": {"mat": "https://example.org/mat#"},
                }
            ]
        },
    }
)


@task.graph()
def workflow(structure: Annotated[Any, structure_meta]):
    return compute_band_structure(structure=structure).result


# %%
# Attaching semantics at runtime
# ------------------------------
# For relations between sockets of different nodes, use ``attach_semantics`` with
# a predicate (subject-first). The same helper attaches label/iri/attributes
# when you pass ``semantics=...``.

from node_graph.semantics import attach_semantics


@task()
def generate(structure):
    return structure


@task()
def compute_density_of_states(structure):
    return 1.0


@task.graph()
def workflow_with_runtime_semantics(
    structure,
) -> Annotated[dict, namespace(output_structure=Any, bands=Any, dos=Any)]:
    mutated = generate(structure=structure).result
    bands = compute_band_structure(structure=mutated).result
    dos = compute_density_of_states(structure=mutated).result
    attach_semantics(
        mutated,
        objects=[bands, dos],
        predicate="emmo:hasProperty",
        semantics={"label": "Generated structure", "iri": "emmo:Material"},
        label="Generated structure",
        context={"emmo": "https://emmo.info/emmo#"},
        socket_label="result",
    )
    return {"output_structure": mutated, "bands": bands, "dos": dos}


# %%
# Tips and use cases
# ------------------
# - Declare socket semantics via ``meta(semantics=...)`` so engines can persist
#   them on produced/consumed ``Data`` nodes.
# - Use dotted socket paths in relations to point at sibling inputs/outputs;
#   the engine resolves them to node references.
# - ``attach_semantics`` appends relations during execution; it records intent on
#   the graph and resolves once data nodes exist.
# - Built-in namespace registry auto-fills ``@context`` when it sees known
#   prefixes (e.g., ``qudt:``); extend it via ``register_namespace(prefix, iri)``.
#   For example, ``register_namespace("mat", "https://example.org/mat#")`` lets
#   you use ``mat:hasProperty`` without repeating the URL in every annotation.
