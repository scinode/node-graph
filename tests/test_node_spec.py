import copy
from node_graph.socket_spec import namespace as ns
from node_graph.node_spec import NodeSpec, hash_spec
from node_graph.executor import NodeExecutor


def test_nodespec_serialize_roundtrip():
    inp = ns(x=int, y=(int, 2))
    out = ns(sum=int)
    ex = NodeExecutor(mode="module", module_path="math", callable_name="hypot")
    spec = NodeSpec(
        identifier="pkg.add",
        catalog="Math",
        inputs=inp,
        outputs=out,
        properties={"p": {"identifier": "node_graph.any", "name": "p"}},
        executor=ex,
        metadata={"k": "v"},
        version="1.0",
    )
    d = spec.to_dict()
    spec2 = NodeSpec.from_dict(copy.deepcopy(d))
    assert spec2.identifier == spec.identifier
    assert spec2.catalog == spec.catalog
    assert spec2.inputs == spec.inputs
    assert spec2.outputs == spec.outputs
    assert spec2.properties == spec.properties
    assert spec2.metadata == spec.metadata
    assert spec2.version == spec.version
    # executor roundtrip: basic fields
    assert spec2.executor.mode == "module"
    assert spec2.executor.module_path == "math"
    assert spec2.executor.callable_name == "hypot"


def test_hash_spec_stability():
    inp = ns(x=int)
    out = ns(y=int)
    h1 = hash_spec("foo", inp, out)
    h2 = hash_spec("foo", inp, out)
    assert h1 == h2

    # change outputs changes hash
    out2 = ns(y=int, z=int)
    h3 = hash_spec("foo", inp, out2)
    assert h3 != h1

    # extra payload affects hash
    h4 = hash_spec("foo", inp, out, extra={"meta": 1})
    assert h4 != h1


def test_nodespec_resolve_base_class_default():
    # Default should be SpecNode (importable)
    s = NodeSpec(identifier="demo.id")
    Base = s._resolve_base_class()

    assert Base.__name__ == "SpecNode"


def test_nodespec_resolve_base_class_custom():
    s = NodeSpec(identifier="demo.id", base_class_path="builtins.object")
    Base = s._resolve_base_class()
    assert Base is object
