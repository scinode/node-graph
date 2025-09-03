from dataclasses import dataclass

WAIT_SOCKET_NAME = "_wait"
OUTPUT_SOCKET_NAME = "_outputs"
MAX_LINK_LIMIT = 1000000

BUILTIN_NODES = ["graph_ctx", "graph_inputs", "graph_outputs"]


@dataclass(frozen=True)
class BuiltinPolicy:
    input_wait: bool = True
    output_wait: bool = True
    default_output: bool = True
