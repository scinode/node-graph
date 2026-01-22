from dataclasses import dataclass

from node_graph.socket import TaggedValue
from node_graph.utils.struct_utils import contains_tagged_value


def test_contains_tagged_value_dataclass():
    @dataclass
    class Payload:
        x: int
        y: object

    tagged = Payload(x=1, y=TaggedValue(2))
    plain = Payload(x=1, y=2)

    assert contains_tagged_value(tagged) is True
    assert contains_tagged_value(plain) is False
