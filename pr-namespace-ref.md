# Socket references for namespace members

Closes #169.

Depends on scinode/node-graph#170 ("Keep an explicitly assigned empty namespace at collection"), merged into this branch. This branch's first draft grew its own `required`-based "keep the namespace even when empty" rule to make `codes.ref("pw")` reach the graph body when `codes={}`; #170 solves the same problem more generally, for *any* explicitly-assigned-but-empty namespace, not just required ones fed to `.ref()`. Depending on it instead of duplicating it also restores a contract the hand-rolled rule had broken: a required namespace never passed to `build()` at all (as opposed to passed as `{}`) now raises `TypeError` again, matching this repo's existing behaviour, instead of silently reaching the body as an empty namespace.

A `@task.graph` body can now wire a namespace member it cannot read — `codes.ref("ph")` — so the socket layer, not a `KeyError`, decides what happens when that member was not provided.

## Problem

A graph body runs eagerly at build time with resolved inputs, so a typed namespace input arrives as a plain mapping of values. Reading a member that the caller did not provide is a bare `KeyError`, wherever in the body it happens:

```python
class Codes(TypedDict):
    pw: orm.AbstractCode
    ph: NotRequired[orm.AbstractCode]   # only some routes need it

@task.graph()
def Dielectric(codes: Codes):
    run_ph(code=codes["ph"])

Dielectric.build(codes={"pw": pw_code})
# KeyError: 'ph'
```

The same graph that never touches `codes` gets the treatment one would want: `run()` reports the unfilled socket by path, together with whatever the annotation declared about it. Touching `codes` loses that, and the two workarounds each give something up:

- Guarding with `if "ph" in codes` silently drops the step, so a typo in the caller's key becomes a missing calculation rather than an error.
- Deferring the lookup to a task (`get(codes, "ph").result`) costs a runtime task per key access and, worse, erases requiredness: the result link fills the downstream required socket, so the missing-input check can never fire and the failure lands mid-run as a `KeyError` inside a task.

## Changes

- A namespace input reaching a graph body is a `TaggedNamespace` — a `dict` that also keeps a handle on its socket. Subscription is untouched: it returns values and raises `KeyError` for an absent member, so `get_builder_from_protocol(codes["pw"], ...)` and every other value-reading pattern keeps working.
- `codes.ref("ph")` returns a `SocketReference`, which never raises for a member that was not provided. Dotted names reach into nested namespaces (`config.ref("codes.pw")`).
- Assigning a reference **directly to a socket** links the two sockets when the member was provided — the same link subscription would have made — so a provided member wired that way behaves identically either way. When the member was not provided, no link is made and the target stays unset: a required target is then reported by the framework's own missing-input check, and an optional one is simply left alone.
- A reference does **not** get to piggyback on a container, though. One buried inside a plain dict/list/tuple/set bound for a leaf socket (`show(opts={"a": codes.ref("ph")})`) is not decomposed by anything on the way in, so it would otherwise be stored as an inert `SocketReference` object instead of being linked or reported. Assigning such a container now raises at build time, naming both the socket that would have received the bad value and the reference's source socket — whether or not the referenced member was actually provided, since the container can't be linked in either case.
- An unfilled target records where it came from in its `unresolved_ref` metadata (`graph_inputs.codes.ph`), which round-trips through `to_dict`/`from_dict` alongside the rest of the socket metadata for a *declared* member. A dynamic (var-kwargs) namespace's unfilled child does not: see Caveats.
- A required namespace now reaches the body even when it was explicitly assigned `{}` (via #170), so `codes.ref("pw")` still works there instead of the body never being called. A namespace never assigned anything at all is a different case and keeps raising `TypeError` for the missing argument, as above.
- `TaggedNamespace` drops its socket handle under `copy.deepcopy`/`pickle` (falling back to a plain `dict`), since the handle is a live graph object that is neither deep-copyable nor picklable; the dict-style `.copy()` method is unaffected, since that is how the framework itself clones a namespace value while keeping its socket.

What the author writes and what a caller then sees:

```python
@task.graph()
def Dielectric(codes: Codes):
    run_ph(code=codes.ref("ph"))

wg = Dielectric.build(codes={"pw": pw_code})   # builds
wg.run()
# MissingRequiredInputsError: Missing required inputs:
#   • run_ph.code
```

## Caveats

- **No late binding.** `ref("ph")` decides whether the member was provided at the moment it is assigned to a target socket, using the state of `codes` at that point in the graph body. Assigning an absent reference over a socket that already holds an explicit value leaves that value in place (with `unresolved_ref` recorded alongside it) rather than clearing it — the target is not made to track the reference afterwards.
- **Dynamic-namespace round-trip loses the diagnostic.** A reference assigned into a `**kwargs`-style dynamic namespace creates a child socket with `unresolved_ref` set, same as a declared member. But `to_dict()` only serialises a dynamic namespace's children that carry a link or a value; an unfilled child carries neither, so it is dropped, and `from_dict()` never recreates it. `run()`/`submit()` check the *in-memory* graph right after `build()`, before any round-trip, so this is reachable only via explicit `to_dict()`/`from_dict()` reconstruction (e.g. persisting and reloading a graph) — not through normal use.
- **A wiring mistake is loud on a provided member and quiet on an absent one.** Assigning a namespace-valued reference into a leaf socket, or a str-valued member into an int-typed one, raises immediately when the member was provided (the ordinary link-time type check fires). When the member is absent, nothing is linked, so that check never runs; the target is simply left required-and-unset, same as any other absent ref, and the mismatch only ever surfaces if the caller later provides the member. This is a gap in how early a wiring mistake is caught, not a case of storing a bad value silently — the target never holds anything wrong.
- **An unresolved reference is a present object to same-scope Python code.** Across a graph/task boundary an absent `ref("x")` behaves as absence — no link, an unfilled socket. But *before* that boundary it is an ordinary Python object: code that assembles a dict with `d["x"] = codes.ref("x")` and then tests `"x" in d` in the same eager scope sees `True` whether or not the member was provided. A conditional-feature-by-code-presence pattern must keep its membership test on the source namespace (`"x" in codes`), not on a dict already holding references — migrating a real production graph hit exactly this once. Worth a doc sentence wherever `ref` is introduced.
- **No static-typing story yet.** A namespace parameter annotated with a `TypedDict` has no `.ref` attribute as far as a type checker is concerned, so every call site is a mypy `attr-defined` error today. Adopting codebases need either a stub/`Protocol` for ref-capable namespaces, a typed free-function form, or blanket ignores — left as a follow-up to settle with the API's final shape.
- **`copy.deepcopy`/`pickle` drop the socket handle on purpose.** Both yield a plain `dict`, the same as `.copy()`'s counterpart would if it also dropped the handle — but `.copy()` keeps it, deliberately: it is the framework's own tool for cloning a namespace value while it is still wired into a graph. `deepcopy`/`pickle` are data-boundary operations instead — the realistic caller is library code (e.g. a protocol builder) treating the namespace as a plain mapping — and a "copy" that silently keeps a live handle into someone else's graph is a bigger surprise than one that degrades to data. Use `.copy()` to keep the socket handle.

## Testing

`tests/test_socket_ref.py` covers the behaviours the feature rests on, each phrased so that a regression in it fails on its own:

- A provided member produces exactly the link subscription produces, and its value reaches the consuming task under the local engine — this is what rules out `ref` becoming a second, divergent wiring path.
- An absent member leaves a required target with no links and no value, carrying `unresolved_ref`; an optional target is left unset without complaint. Reverting the "do not link when unprovided" branch fails several tests, so these do discriminate.
- Subscription is asserted unchanged in the same bodies that use `ref`, including the `KeyError` for an absent member.
- `to_dict`/`from_dict` round-trips a graph with a resolved link and a graph with an unresolved reference (for a *declared* member; see Caveats for the dynamic-namespace gap).
- A required namespace omitted entirely from `build()` raises `TypeError`, for both a mixed required/optional shape and an all-members-optional shape — `Options(TypedDict, total=False)` — where the namespace itself is still required even though nothing inside it is.
- A `SocketReference` nested in a dict or a list bound for a leaf socket raises at build time, naming the target and source sockets, whether or not the referenced member was provided; a negative control (the check disabled via monkeypatch) reproduces the pre-fix silent-garbage behaviour, and a raw (non-reference) socket nested the same way is confirmed unaffected.
- `TaggedNamespace` under `copy.deepcopy`/`pickle`/`copy.copy` yields a plain `dict`; its own `.copy()` method still yields a `TaggedNamespace` with the socket intact.

Full suite (this branch's own `tests/`, pure node-graph, no AiiDA): 335 passed, against 309 on base `main` (8d85e61) and 321 on this branch before this round of fixes (868e4991) — all three measured in the same environment. The one pre-existing skip (`test_await_forbidden`) is a missing async pytest plugin in that environment, unrelated to this change.

Beyond the unit tests, I ran the motivating case end to end in aiida-workgraph on a throwaway profile (`demo_namespace_ref.py`, 5/5): with the optional code absent the build succeeds and `run()` raises `MissingRequiredInputsError` naming `run_code.code`; with it provided the graph runs to completion and the task receives the code. The deferred-lookup workaround, on the same graph shape, passes the input check and fails mid-run instead — which is the behaviour this feature is meant to replace. The omitted-namespace and stored-reference fixes were re-verified at the aiida-workgraph level too (an all-optional-members `Options` namespace omitted entirely now raises `TypeError` there as well; a ref nested in a leaf-bound dict raises there too, both provided and absent).
