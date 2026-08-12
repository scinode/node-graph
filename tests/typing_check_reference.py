"""Typed usage of ``reference()`` on a TypedDict-annotated graph body.

Checked out of band with ``mypy --strict`` (the repo has no mypy step in its
own test/pre-commit config to hook a subprocess test into; see the PR body
for the invocation and result). Every TypedDict is assignable to
``Mapping[str, object]``, so this call site needs no cast and no escape
hatch. ``codes.reference("pw")`` on the same ``Codes`` value is an
attr-defined error under ``--strict``, since ``TypedDict`` declares no
``reference`` method — that is the gap this function closes.
"""

from typing import TypedDict

from node_graph import reference
from node_graph.socket import SocketReference


class Codes(TypedDict):
    pw: str


def wire_pw(codes: Codes) -> SocketReference:
    return reference(codes, "pw")
