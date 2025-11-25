"""
Ontology-aware semantics
========================

NodeGraph captures structural provenance out of the box, but structural links
do not explain what a piece of data *means*. Semantics add domain ontology
context—labels, IRIs, units, and relations—so every ``Data`` node carries a
machine-readable JSON-LD breadcrumb. This page introduces ontologies, shows
how NodeGraph stores semantics, and provides runnable examples.
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
# How NodeGraph stores semantics
# ------------------------------
# 1. **Authoring**: sockets declare ``meta(semantics={...})`` (label, iri,
#    rdf_types, context, attributes, relations). The graph keeps these in
#    ``NodeGraph.semantics_buffer`` so they survive serialization.
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

from typing import Annotated
from node_graph import node
from node_graph.socket_spec import meta, namespace


@node()
def AnnotateSemantics(
    energy: float,
) -> Annotated[
    float,
    meta(
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
    ),
]:
    return energy


# %%
# Cross-socket relation example
# -----------------------------
# One can also declare relations between sockets using dotted paths to refer to sibling inputs/outputs.
# For example, the following workflow declares that the input
# ``structure`` has a relation ``mat:hasProperty`` pointing to the output of the
# ``compute_band_structure`` node.


@node()
def compute_band_structure(structure):
    return 1.0


@node.graph(
    inputs=namespace(
        structure=meta(
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
    )
)
def workflow(structure):
    return compute_band_structure(structure=structure).result


# %%
# Attaching semantics at runtime
# ------------------------------
# For relations between sockets of different nodes, use ``attach_semantics``.

from node_graph.semantics import attach_semantics


@node()
def generate(structure):
    return structure


@node()
def compute_density_of_states(structure):
    return 1.0


@node.graph()
def workflow_with_runtime_semantics(structure):
    mutated = generate(structure=structure).result
    bands = compute_band_structure(structure=mutated).result
    dos = compute_density_of_states(structure=mutated).result
    attach_semantics(
        "mat:hasProperty",
        mutated,
        bands,
        dos,
        label="Generated structure",
        context={"mat": "https://example.org/mat#"},
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
