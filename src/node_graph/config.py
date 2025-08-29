import dataclasses


@dataclasses.dataclass(frozen=True)
class BuiltinSocketNames:
    wait: str = "_wait"
    output: str = "_outputs"


MAX_LINK_LIMIT = 1000000
