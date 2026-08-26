# simplestate redesign: builder + state-as-function API

**Date:** 2026-08-26
**Status:** Approved in discussion, pending spec review

## Goal

Replace the operator DSL (`m["red"] + "next" >> "green"`) with a fluent,
IDE-friendly API. The old DSL had three flaws: build-time and run-time shared
mutable state (defining a transition could teleport a running machine),
the `+`/`>>` chain held dangling state and failed silently when misused, and
string-based states made typos silent runtime no-ops.

## Design

### States are functions

A state is a plain function. Its `__name__` is the state's identity; its body
is the state's behavior. A generator function splits enter/exit at `yield`
(the `contextlib.contextmanager` idiom); a plain function is enter-only.

```python
def uploading(prev, **ctx):
    if prev == "failed":
        print("retrying...")
    bar = ProgressBar()      # locals naturally span enter -> exit
    yield
    bar.close()              # exit
```

- Signature: `(prev, **ctx)` where `prev` is the previous state's **name**
  (a string; `""` for the initial entry) and `**ctx` is whatever keyword
  arguments were passed to `handle()`.
- One generator instance per visit — locals reset on re-entry.
- This subsumes enter/exit hooks and dispatch-on-incoming-state: branch on
  `prev` inside the function.

### Function references, not strings

The API takes the state functions themselves — `.at(idle)`,
`goto=uploading`. A typo is a `NameError` (red in the IDE before you run),
autocomplete and refactor-rename work for free.

### Events are Literal-typed

`StateMachineBuilder` is generic over the event type:

```python
type UploadEvent = Literal["upload", "ok", "error", "retry", "cancel"]
StateMachineBuilder[UploadEvent](...)
```

The parameter flows through `.on(event, ...)` and `handle(event)`, so both
definitions and call sites across the app are checked, with literal
autocomplete. Unparameterized use means `E = str` — quick scripts need no
ceremony.

### Builder -> build() -> state node

```python
state = (
    StateMachineBuilder[UploadEvent](idle, uploading, failed, done)
    .at(idle).on("upload", goto=uploading)
    .at(uploading).on("ok", goto=done).on("error", goto=failed)
    .at(failed).on("retry", goto=uploading)
    .at_any().on("cancel", goto=idle)
    .build(initial=idle)
)
```

- `.at(fn)` scopes subsequent `.on()` calls to that state; `.at_any()` scopes
  them to the wildcard (any-state transitions, lower priority than
  state-specific ones — same semantics as the old `"?"`).
- `.build(initial=...)` validates the graph — every `goto` target and the
  initial state must be registered (constructor args; functions referenced
  only via `goto=` are auto-registered) — raising `ValueError` on failure.
  Build runs the initial state's enter and returns its state node. There is
  no separate `start()`.
- The transition graph is immutable after build.

### The state node (there is no machine object)

`build()` and `handle()` return a **state node** — the machine's current
face. API:

- `.value` — the state name (str).
- `str()` / `repr()` — prints the state name nicely.
- `.handle(event, **ctx)` — runs the current node's exit, the target node's
  enter (passing `prev` and `**ctx`), and returns the **next state node**
  (functional style; the caller reassigns).

### Error behavior

Exception classes live in `simplestate/exceptions.py` and are imported from
there (`from simplestate.exceptions import ...`), not from the package root:

```python
class SimplestateError(Exception): ...
class InvalidGraphError(SimplestateError): ...   # raised by build()
class UnknownEventError(SimplestateError): ...   # raised by handle()
class StaleStateError(SimplestateError): ...     # raised by handle()
```

**Fluent error routing.** Error handling is declared on the builder, not
try/excepted at call sites:

```python
.on_error(TimeoutError | ConnectionError, goto=failed)   # unions welcome
.on_error(UnknownEventError, goto=idle)
```

`on_error` accepts a single exception type or a PEP 604 union
(`A | B`); matching is a plain `isinstance` check, which supports unions
natively since Python 3.10.

- When a registered exception type is raised inside a state function (enter
  or exit), or when the machine would raise `UnknownEventError`, the machine
  routes to the `goto` state instead, passing the exception as `error=` in
  the context. First registered `isinstance` match wins.
- Unregistered exception types propagate normally.
- An exception raised while entering the error-route state itself propagates
  (no recursive routing).
- Not routable (always raise, programming errors): `StaleStateError` —
  `handle()` on a node that has already transitioned out (its exit already
  ran; history does not fork) — and `InvalidGraphError` from `build()`
  (unknown initial state, or an `on_error` goto that is not a known state).
- With no `on_error` registered for it, an unhandled event raises
  `UnknownEventError` (old behavior was silent ignore; `.at_any()` covers
  deliberate catch-alls). Carries the state name and event.

## What is removed

- The operator DSL (`__getitem__`, `__add__`, `__rshift__`).
- `State` class in its current form, `add_callbacks`, `start()`,
  `m.current` / `m.previous` string attributes.
- Silent ignore of unknown events.

No backward compatibility is kept; existing tests are rewritten against the
new API.

## Testing

Rewrite `tests/test_state_machine.py` to cover: linear flow, wildcard
transitions, context forwarding to enter, generator exit runs on transition
out, per-visit generator freshness, `prev` values (including `""` initially),
build-time validation errors, `UnknownEventError`, `StaleStateError`, and
plain-function (yield-less) states.
