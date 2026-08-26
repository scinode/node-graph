✨ Take a task's socket contract from a Pydantic model

## Problem

A task's inputs are described twice today: once in the signature, where the socket layer reads types, and once in whatever validation the body does after the fact. Anything the socket layer cannot express has no home. A `Decimal` amount, a value that must be one of three, two inputs whose order matters, a field that must be at most 100 — the socket layer types all of these as `any`, so a wrong value is written at build time, stored, submitted, and discovered when the body raises. `SocketSpec.from_model` already expands a Pydantic model into sockets, but it reads the model's field types and defaults and then drops the model: field validators, cross-field rules and computed coercion never run.

This makes the model the contract, not just the shape.

```python
class SpanInputs(BaseModel):
    low: int
    high: int = Field(le=100)

    @model_validator(mode="after")
    def ordered(self):
        if self.low >= self.high:
            raise ValueError("low must be below high")
        return self

@task(input_model=SpanInputs)
def span(low, high):
    return high - low
```

`SpanInputs` now declares `span`'s sockets, their defaults and their requiredness, and its rules are held to at three moments: the line that wires the task, the expansion of a `@task.graph`, and the run edge. The body keeps a plain signature and receives plain Python — for an `Enum` field the member, for a `Decimal` field a `Decimal`.

## Changes

**The spec comes from the model.** `spec_from_model` overlays on `from_model` what the model knows and `from_model` does not: a field's requiredness (`from_model` leaves every field required, so a field defaulting to `None` reads as a missing input), a default rendered JSON-safe (the spec is persisted with the task), and `dict[str, T]` read as a typed dynamic namespace, so each key of a runtime-sized mapping becomes a socket of its own. The dotted class path `from_model` records is left out: the model is reached through the task's executor, so a class that moves does not break stored data.

**Model and signature are checked against each other at decoration**, and any disagreement raises `ModelContractError` naming the offender — a field no parameter takes, a parameter no field declares, an annotation that contradicts its field, `*args`/`**kwargs`, and a default written in the signature ("defaults live in the model — move it").

**Checkpoint A, at the task call** (`BaseHandle.__call__`, between `_prepare_call_inputs` and `set_inputs`): every value written that is not a socket reference is checked against the field it goes to, so a bad literal fails at the line that wrote it. The model runs as a flat shadow — `create_model` with no base, every field re-annotated `Annotated[T, WrapValidator(...)]` recursively through containers, nested models and union arguments — and the instance is discarded, the original values passed on. Both are load-bearing: pydantic strips the proxy a tagged value wears for nearly every field type, and a stripped value is a literal, so forwarding the validated copy would turn a link into a copy of the graph input's current value.

The boundary is worth stating plainly, because it is the price of the flat shadow: **a user's `@field_validator` and `@model_validator` do not fire at A**. Inheriting them would run a rule written for resolved inputs against a placeholder that forwards comparisons, so it would fail — or pass — for the wrong reason. B and C catch what A does not.

**Checkpoint B, at graph expansion** (`materialize_graph`, after the inputs are resolved and deserialized): a `@task.graph`'s inputs are values by then, so the real model runs, cross-field rules and all. An untagged *copy* is validated and discarded and the body is handed the originals, because the body turns those tags into links and a fresh object carries none. All three expansion paths funnel through `materialize_graph` — a handle's `build()`, the engine's subgraph, and aiida-workgraph's graph task — so one hook covers all of them.

```python
@task.graph(input_model=SpanInputs)
def span_graph(low, high):
    return span(low=low, high=high)

span_graph.build(low=9, high=3)
# node_graph.input_model.TaskInputValidationError: Graph 'span_graph' got inputs SpanInputs rejects:
#   Value error, low must be below high
```

**Checkpoint C, at the leaf run edge:** the executor is a wrapper that validates the assembled inputs and hands the body `dict(validated)`. `output_model=` is the mirror: it declares the output sockets and validates the return value, so a missing or mistyped output fails at the task that produced it rather than at the task that consumed it. `output_model=` on `@task.graph` is refused — a graph returns socket references, so there is nothing to validate.

**Validation may change how a value is spelled, never what it says.** `'60'` may become a `Decimal` and a list a tuple; deriving or rewriting an input is refused, because the body would then run on a value that never reached storage. The comparison is made through a plain twin of the model — same fields and constraints, every user rule absent — so a `field_serializer` (which renders, and so is representation) stays out of it. The rule in one line: a validator must be a no-op on values that are already resolved. `str.upper()` on `'SILICON'` passes; on `'silicon'` it raises `ModelDerivedValueError` naming the field and the task.

**Without either keyword nothing changes.** `apply_models` is the identity, and a task declared the usual way takes exactly the path it took before.

## Testing

`tests/test_input_model.py`, 49 tests. Each checkpoint has a test that passes with its hook disabled, so the test is measuring the hook and not some other layer:

- **A** is parameterized over three fields the type map reads as `any` or `annotated` — a `Decimal` given nonsense, a `tuple[int, int]` given three items, a `Field(gt=0)` given `-1`. With the hook stubbed out, all three build without complaint. This is also the honest bound on what A adds: a leaf socket typed `int` already refuses a bad literal at `set_inputs`, so for those A changes the message, not the outcome.
- **B**'s control is a cross-field rule over two ints, each of which any layer would accept on its own; with the hook stubbed out, `build(low=9, high=3)` succeeds. A second test drives a subgraph whose bound is produced by an upstream task under `LocalEngine`, which is the first moment that value exists.
- **C** asserts the body never ran: a list the body appends to stays empty when the model rejects the inputs.
- **Link preservation** builds the same graph twice, once with A stubbed out, and compares every link; a companion test asserts `validate_wiring_inputs` hands back the very objects it was given, by `id`.
- **Content invariance** is tested in both directions: a derivation given an already-correct value passes, the same derivation given a wrong one raises and names the field, and `Decimal`, `Enum` and tuple coercions all pass.
- **The documented limits are tests too**, so they cannot rot silently: a field validator capping a value does not fire at A, and a `mode='before'` normalizer is not honoured there — with the fix (a widened `list[int] | list[list[int]]`) shown working beside it.

Full suite: 412 passed, 1 skipped (363 before this branch, 49 new).
