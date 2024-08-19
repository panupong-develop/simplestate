# simplestate

**Simplestate** helps developers create and manage finite state machines in the simplest way possible—focusing solely on states and transitions, leaving out complex event systems.

## Features

- Focus on states and transitions.
- Minimalistic and easy to use.
- Supports entering-state handlers for additional functionality.

## Installation

To install simplestate, 

use poetry:

```bash
poetry add simplestate
```

use pip:
```bash
pip install simplestate
```

## Usage Example

Here's a basic example of using **simplestate**:

m[`state`] + `action` >> `next_state`

```python
from simplestate import StateMachine

m = StateMachine("loading")          # Define the machine with an initial state
m["loading"] + "error" >> "failed"   # Transition from loading to failed on "error"
m["loading"] + "ok"    >> "success"  # Transition from loading to success on "ok"
m["?"]       + "back"  >> "loading"  # Any state transitions to loading on "back"

# Start the machine
m.start()  # adjust inital state by this m.start(at_state="ok")
assert m.current == "loading"

# Trigger transitions
m.handle("ok")
assert m.current == "success"

m.handle("back")
assert m.current == "loading"

m.handle("back")
assert m.current == "loading"

# Trigger transitions with context
m.handle("error", error="Something went wrong")
assert m.current == "failed"
```

## Why Simplestate?

The goal of **simplestate** is to keep finite state machines simple and focused. By eliminating complex event systems, you can easily manage states and transitions while keeping the code testable and maintainable.

### Event Handling on State Entry

Simplestate allows event handling when entering a state using `.add_callbacks()`. These callbacks take `previous` and an optional `**input_context`.
```python
# Add handlers for entering states
m.add_callbacks({
    "loading": lambda previous: print(f"{previous} >> loading"),
    "failed": lambda previous, **input_context: print(f"{previous} >> failed: {input_context['error']}"),
    "success": lambda previous: print(f"{previous} >> success"),
})
```

## FAQ

**Q: How can I handle state exit events?**  
A: You can use the entering handler for the next state to handle actions when leaving the previous state.

```python
def on_state_x(previous, **input_context):
    if previous == "a":
        do_this()
    elif previous == "b":
        do_that()
```

**Q: Can I represent the state machine as a class?**  
A: Yes! Think of simplestate as a state manager. You can compose it within your own class for handling side effects:

```python
class TrafficLight:
    def __init__(self):
        m = StateMachine("red")
        m["red"]    + "next" >> "green"
        m["green"]  + "next" >> "yellow"
        m["yellow"] + "next" >> "red"
        m.start()

        self.machine = m

    def display(self) -> str:
        return self.machine.current

    def next(self) -> None:
        self.machine.handle("next")

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
