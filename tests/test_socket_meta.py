from node_graph.socket_meta import SocketMeta


def test_socket_meta_semantics_roundtrip():
    semantics = {
        "label": "Potential energy",
        "iri": "qudt:PotentialEnergy",
        "context": {"qudt": "http://qudt.org/schema/qudt/"},
    }
    meta = SocketMeta(help="h", semantics=semantics)

    payload = meta.to_dict()
    assert payload["semantics"] == semantics

    restored = SocketMeta.from_dict(payload)
    assert restored.semantics == semantics
    assert restored.semantics is not semantics


def test_socket_meta_moves_semantics_out_of_extras():
    raw = {
        "extras": {
            "semantics": {"label": "Potential energy"},
            "unit": "eV",
        }
    }
    meta = SocketMeta.from_dict(raw)

    assert meta.semantics == {"label": "Potential energy"}
    assert "semantics" not in meta.extras
    assert meta.extras["unit"] == "eV"
