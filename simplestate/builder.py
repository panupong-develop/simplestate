import inspect
from typing import Any, Callable, Generator, Generic, TypeVar

from .exceptions import InvalidGraphError, StaleStateError, UnknownEventError

StateFn = Callable[..., Any]
E = TypeVar("E", bound=str)  # event type, e.g. Literal["upload", "ok"]
ExcTypes = Any  # an exception type or a PEP 604 union of them

_ANY = "..."  # reserved transitions key for at_any()


class StateNode(Generic[E]):
    def __init__(
        self,
        fn: StateFn,
        transitions: dict[str, dict[str, StateFn]],
        error_routes: list[tuple[ExcTypes, StateFn]],
    ):
        self._fn = fn
        self._transitions = transitions
        self._error_routes = error_routes
        self._gen: Generator[None, str, Any] | None = None
        self._result: Any = None  # plain state's enter return, carried on exit
        self._stale = False

    @property
    def value(self) -> str:
        return self._fn.__name__

    def __str__(self) -> str:
        return self.value

    def __repr__(self) -> str:
        return f"<state: {self.value}>"

    def print_graph(self) -> None:
        lines = []
        targets: list[str] = []
        for src, events in self._transitions.items():
            for event, goto in events.items():
                marker = ">" if src == self.value else " "
                lines.append(f"{marker} {src} --{event}--> {goto.__name__}")
                if goto.__name__ not in targets:
                    targets.append(goto.__name__)
        for name in targets:
            if name not in self._transitions:
                marker = ">" if name == self.value else " "
                lines.append(f"{marker} {name} (terminal)")
        print("\n".join(lines))

    def _enter(self, prev: str, **ctx: Any) -> None:
        if inspect.isgeneratorfunction(self._fn):
            self._gen = self._fn(prev, **ctx)
            next(self._gen)  # run enter, park at yield
        else:
            self._result = self._fn(prev, **ctx)

    def _exit(self, next_value: str) -> Any:
        """Run exit; return the value this state hands to the next one."""
        if self._gen is not None:
            gen, self._gen = self._gen, None
            try:
                gen.send(next_value)  # run exit
            except StopIteration as stop:
                return stop.value  # generator's `return x`
            return None
        return self._result

    def _spawn(self, fn: StateFn) -> "StateNode[E]":
        return StateNode(fn, self._transitions, self._error_routes)

    def handle(self, event: E, **ctx: Any) -> "StateNode[E]":
        if self._stale:
            raise StaleStateError(f"'{self.value}' node already transitioned out")
        target = self._transitions.get(self.value, {}).get(
            event
        ) or self._transitions.get(_ANY, {}).get(event)
        try:
            if target is None:
                raise UnknownEventError(
                    f"state '{self.value}' has no transition for event '{event}'"
                )
            carried = self._exit(target.__name__)
            self._stale = True
            if carried is not None:
                ctx.setdefault("prev_returned", carried)
            node = self._spawn(target)
            node._enter(self.value, **ctx)
            return node
        except Exception as exc:
            goto = self._match_error_route(exc)
            if goto is None:
                raise
            self._stale = True
            node = self._spawn(goto)
            node._enter(self.value, error=exc, **ctx)  # unrouted: no recursion
            return node

    def _match_error_route(self, exc: Exception) -> StateFn | None:
        for exc_types, goto in self._error_routes:
            if isinstance(exc, exc_types):
                return goto
        return None


class StateMachineBuilder(Generic[E]):
    def __init__(self, *states: StateFn):
        self._known = {fn.__name__ for fn in states}
        self._transitions: dict[str, dict[str, StateFn]] = {}
        self._error_routes: list[tuple[ExcTypes, StateFn]] = []
        self._at: str | None = None

    def at(self, state: StateFn) -> "StateMachineBuilder[E]":
        self._known.add(state.__name__)
        self._at = state.__name__
        return self

    def at_any(self) -> "StateMachineBuilder[E]":
        self._at = _ANY
        return self

    def on(self, event: E, goto: StateFn) -> "StateMachineBuilder[E]":
        if self._at is None:
            raise InvalidGraphError("on() requires a preceding at() or at_any()")
        self._known.add(goto.__name__)
        self._transitions.setdefault(self._at, {})[event] = goto
        return self

    def on_error(self, exc_types: ExcTypes, goto: StateFn) -> "StateMachineBuilder[E]":
        self._known.add(goto.__name__)
        self._error_routes.append((exc_types, goto))
        return self

    def build(self, initial: StateFn) -> StateNode[E]:
        if initial.__name__ not in self._known:
            raise InvalidGraphError(
                f"initial state '{initial.__name__}' is not a known state"
            )
        node = StateNode(initial, self._transitions, self._error_routes)
        node._enter("")
        return node
