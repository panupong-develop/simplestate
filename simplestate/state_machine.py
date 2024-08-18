from typing import Any, Callable
from .state import State


class StateMachine:
    def __init__(self, initial_state: str):
        self._states: dict[str, State] = {}
        self.previous: str = ""
        self.current: str = initial_state

        # for building state transitions
        self._any_state_transitions: dict[str, str] = {}
        self._initial_state: str = initial_state
        self._current_input: str = ""
        self._add_state(initial_state)
        self._callbacks: dict[str, Callable[[str, Any], None]] = {}

    def _add_state(self, name: str) -> "StateMachine":
        if name not in self._states:
            self._states[name] = State(name)
        if not self._initial_state:
            self._initial_state = name
        return self

    def _add_transition(self, input_name: str, next_state: str) -> "StateMachine":
        self._states.setdefault(next_state, State(next_state))

        if self.current == "?":
            self._any_state_transitions[input_name] = next_state
        else:
            if self.current not in self._states:
                raise ValueError(f"State {self.current} does not exist.")
            self._states[self.current].add_transition(input_name, next_state)
        return self

    def _set_state(self, name: str) -> None:
        self._states.setdefault(name, State(name))
        self.current = name

    def __getitem__(self, state_name: str) -> "StateMachine":
        self._set_state(state_name)
        return self

    def __add__(self, input_name: str) -> "StateMachine":
        self._current_input = input_name
        return self

    def __rshift__(self, next_state: str) -> "StateMachine":
        self._add_transition(self._current_input, next_state)
        return self

    def handle(self, input_name: str, **input_context: Any) -> None:
        state = self._states[self.current]
        next_state = state.transitions.get(input_name)
        if not next_state:
            next_state = self._any_state_transitions.get(input_name)
        if next_state:
            # call handler before update
            if next_action := self._callbacks.get(next_state):
                next_action(self.current, **input_context)
            # set state
            self.previous = self.current
            self.current = next_state

    def add_callbacks(
        self,
        callbacks: dict[str, Callable[[str, Any], None]],
    ) -> "StateMachine":
        self._callbacks = callbacks
        return self

    def start(self, at_state: str | None = None) -> "StateMachine":
        if at_state:
            self._initial_state = at_state

        if not self._initial_state:
            raise ValueError("Initial state not set.")

        if action := self._callbacks.get(self._initial_state):
            action(self.previous)

        self.current = self._initial_state
        return self
