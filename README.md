# simplestate

**Simplestate** helps developers create and manage finite state machines in the simplest way possible — states are plain functions, transitions are declared fluently, and your IDE catches mistakes before you run.

## Features

- **States are functions** — the function name is the state, the body is the behavior.
- **Enter/exit in one place** — code before `yield` runs on enter, code after runs on exit.
- **IDE-friendly** — transitions reference the functions themselves; a typo is an instant `NameError`, and events can be `Literal`-typed for autocomplete and type checking.
- **Fail loudly** — unknown events and invalid graphs raise dedicated exceptions, or route to an error state you declare.
- **Visualize** — `print_graph()` draws the machine as a tree, marking where you are.

## Installation

use poetry:

```bash
poetry add simplestate
```

use pip:
```bash
pip install simplestate
```

## Usage Example

```python
from typing import Literal
from simplestate import StateMachineBuilder

type UploadEvent = Literal["upload", "ok", "error", "retry", "cancel"]

# States are functions. Code before `yield` runs on enter, after on exit.
def idle(prev, **ctx):
    print("waiting for work")

def uploading(prev, **ctx):
    if prev == "failed":
        print("retrying...")
    print("upload started")
    yield
    print("upload finished or aborted")   # exit

def failed(prev, error=None, **ctx):
    print(f"upload failed: {error}")

def done(prev, **ctx):
    print("all done")

state = (
    StateMachineBuilder[UploadEvent]()
    .at(idle).on("upload", goto=uploading)
    .at(uploading).on("ok", goto=done).on("error", goto=failed)
    .at(failed).on("retry", goto=uploading)
    .at_any().on("cancel", goto=idle)          # from any state
    .on_error(TimeoutError, goto=failed)       # exceptions route to a state
    .build(initial=idle)                       # validates the graph, enters `idle`
)

state = state.handle("upload")     # handle() returns the NEXT state
print(state)                       # uploading
state = state.handle("error", error="connection lost")
assert state.value == "failed"
state = state.handle("retry").handle("ok")
assert state.value == "done"
```

## Why Simplestate?

The goal of **simplestate** is to keep finite state machines simple and focused. A state's whole story — enter behavior, exit behavior, local variables that span the visit — lives in one ordinary Python function. The machine itself is just the state object in your hand.

### Enter and exit

A generator state splits at `yield`: everything before runs when the state is entered, everything after runs when it is left. Locals survive from enter to exit. A plain function (no `yield`) is enter-only.

```python
def uploading(prev, **ctx):
    bar = ProgressBar()   # enter
    yield
    bar.close()           # exit
```

The enter function receives `prev` (the previous state's name, `""` on first entry) plus any keyword arguments passed to `handle()`:

```python
state.handle("error", reason="timeout")   # -> failed(prev, reason="timeout")
```

### Passing values forward

A state can hand a value to its successor — `return` it (after `yield` for generator states). The next state receives it as `prev_returned`:

```python
def uploading(prev, **ctx):
    yield
    return {"bytes": 42}

def done(prev, prev_returned, **ctx):
    print(prev_returned)   # {'bytes': 42}
```

### Error handling

Declare error routing fluently — no try/except at call sites:

```python
.on_error(TimeoutError | ConnectionError, goto=failed)   # unions welcome
```

When a registered exception is raised inside a state function, the machine routes to that state instead, passing the exception as `error=`. Unregistered exceptions propagate. Everything else fails loudly with exceptions from `simplestate.exceptions`:

- `UnknownEventError` — the current state has no transition for the event (routable via `on_error`).
- `StaleStateError` — `handle()` on a state object you already transitioned out of.
- `InvalidGraphError` — bad machine definition, raised at `build()`.
- `SimplestateError` — base class for all of the above.

### Visualizing the machine

```python
state.print_graph()
```

```
current: uploading

● [idle]
  └── upload --> [uploading] *
                 ├── ok --> [done] ◉
                 └── error --> [failed]
                               └── retry --> [uploading] ↺

any state:
	cancel --> [idle]
```

`●` start, `◉` terminal, `*` current state, `↺` already shown above.

## FAQ

**Q: Where did the machine object go?**
A: `build()` returns the initial state object, and each `handle()` returns the next one — the current state *is* the machine. Reassign as you go: `state = state.handle("ok")`. Using an old state object raises `StaleStateError`.

**Q: Do I have to list states anywhere?**
A: No. Any function used in `.at()`, `goto=`, or `on_error()` is registered automatically. `StateMachineBuilder(idle)` accepts states as arguments only for the rare state referenced nowhere else.

**Q: Can I represent the state machine as a class?**
A: Yes! Compose it within your own class:

```python
import time
from simplestate import StateMachineBuilder

def red(prev, **ctx): ...
def green(prev, **ctx): ...
def yellow(prev, **ctx): ...

class TrafficLight:
    def __init__(self):
        self.state = (
            StateMachineBuilder()
            .at(red).on("next", goto=green)
            .at(green).on("next", goto=yellow)
            .at(yellow).on("next", goto=red)
            .build(initial=red)
        )

    def display(self) -> str:
        return self.state.value

    def next(self) -> None:
        self.state = self.state.handle("next")

if __name__ == '__main__':
    light = TrafficLight()

    while True:
        state = light.display()
        print(state)

        # pause for a few seconds
        match state:
            case "red" | "green":
                time.sleep(30)
            case "yellow":
                time.sleep(5)

        # transition
        light.next()
```

## Tests

To run the tests:

```bash
poetry install --with test
poetry run pytest
```

## Contribution

Contributions are welcome! Feel free to open an issue or submit a pull request.

1. Install [devcontainer](https://code.visualstudio.com/docs/devcontainers/containers)
2. Open this project in dev container
3. Run `poetry shell`
4. Run `poetry install --with test`
5. Run `poetry run pytest`

## License

This project is licensed under a free, open-source license.
