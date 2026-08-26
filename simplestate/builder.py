import inspect
from typing import Any, Callable, Generator

from .exceptions import InvalidGraphError, StaleStateError, UnknownEventError

StateFn = Callable[..., Any]

_ANY = "?"  # reserved transitions key for at_any()


class StateNode:
    def __init__(self, fn: StateFn, transitions: dict[str, dict[str, StateFn]]):
        self._fn = fn
        self._transitions = transitions
        self._gen: Generator[None, str, None] | None = None
        self._stale = False

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
        if self._stale:
            raise StaleStateError(
                f"'{self.value}' node already transitioned out"
            )
        target = self._transitions.get(self.value, {}).get(
            event
        ) or self._transitions.get(_ANY, {}).get(event)
        if target is None:
            raise UnknownEventError(
                f"state '{self.value}' has no transition for event '{event}'"
            )
        self._exit(target.__name__)
        self._stale = True
        node = StateNode(target, self._transitions)
        node._enter(self.value, **ctx)
        return node


class StateMachineBuilder:
    def __init__(self, *states: StateFn):
        self._known = {fn.__name__ for fn in states}
        self._transitions: dict[str, dict[str, StateFn]] = {}
        self._at: str | None = None

    def at(self, state: StateFn) -> "StateMachineBuilder":
        self._known.add(state.__name__)
        self._at = state.__name__
        return self

    def at_any(self) -> "StateMachineBuilder":
        self._at = _ANY
        return self

    def on(self, event: str, goto: StateFn) -> "StateMachineBuilder":
        self._known.add(goto.__name__)
        self._transitions.setdefault(self._at, {})[event] = goto
        return self

    def build(self, initial: StateFn) -> StateNode:
        if initial.__name__ not in self._known:
            raise InvalidGraphError(
                f"initial state '{initial.__name__}' is not a known state"
            )
        node = StateNode(initial, self._transitions)
        node._enter("")
        return node
