import inspect
from typing import Any, Callable, Generator

from .exceptions import UnknownEventError

StateFn = Callable[..., Any]


class StateNode:
    def __init__(self, fn: StateFn, transitions: dict[str, dict[str, StateFn]]):
        self._fn = fn
        self._transitions = transitions
        self._gen: Generator[None, str, None] | None = None

    @property
    def value(self) -> str:
        return self._fn.__name__

    def __str__(self) -> str:
        return self.value

    def _enter(self, prev: str, **ctx: Any) -> None:
        if inspect.isgeneratorfunction(self._fn):
            self._gen = self._fn(prev, **ctx)
            next(self._gen)  # run enter, park at yield
        else:
            self._fn(prev, **ctx)

    def _exit(self, next_value: str) -> None:
        if self._gen is not None:
            try:
                self._gen.send(next_value)  # run exit
            except StopIteration:
                pass
            self._gen = None

    def handle(self, event: str, **ctx: Any) -> "StateNode":
        target = self._transitions.get(self.value, {}).get(event)
        if target is None:
            raise UnknownEventError(
                f"state '{self.value}' has no transition for event '{event}'"
            )
        self._exit(target.__name__)
        node = StateNode(target, self._transitions)
        node._enter(self.value, **ctx)
        return node


class StateMachineBuilder:
    def __init__(self, *states: StateFn):
        self._states = list(states)
        self._transitions: dict[str, dict[str, StateFn]] = {}
        self._at: StateFn | None = None

    def at(self, state: StateFn) -> "StateMachineBuilder":
        self._at = state
        return self

    def on(self, event: str, goto: StateFn) -> "StateMachineBuilder":
        self._transitions.setdefault(self._at.__name__, {})[event] = goto
        return self

    def build(self, initial: StateFn) -> StateNode:
        node = StateNode(initial, self._transitions)
        node._enter("")
        return node
