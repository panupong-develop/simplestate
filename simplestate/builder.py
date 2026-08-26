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
        initial: str,
    ):
        self._fn = fn
        self._transitions = transitions
        self._error_routes = error_routes
        self._initial = initial
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
        # ponytail: BFS-tree layout — tree edges drawn, the rest listed below;
        # real edge routing if machines ever outgrow this.
        tree: dict[str, list[tuple[str, str]]] = {}
        extra: list[str] = []
        layers: list[list[str]] = [[self._initial]]
        seen = {self._initial}
        frontier = [self._initial]
        while frontier:
            nxt: list[str] = []
            for src in frontier:
                for event, goto in self._transitions.get(src, {}).items():
                    tgt = goto.__name__
                    if tgt not in seen:
                        seen.add(tgt)
                        nxt.append(tgt)
                        tree.setdefault(src, []).append((event, tgt))
                    else:
                        extra.append(f"\t{src} --{event}--> {tgt}")
            if nxt:
                layers.append(nxt)
            frontier = nxt

        center: dict[str, int] = {}
        boxes: list[tuple[str, str, str]] = []
        for layer in layers:
            top, mid, bottom = "", "", ""
            x = 0
            for name in layer:
                label = f"{name} *" if name == self.value else name
                width = len(label) + 4
                pad = " " * (x - len(top))
                top += pad + "┌" + "─" * (width - 2) + "┐"
                mid += pad + f"│ {label} │"
                bottom += pad + "└" + "─" * (width - 2) + "┘"
                center[name] = x + width // 2
                x += width + 2
            boxes.append((top, mid, bottom))

        lines = [f"current: {self.value}", ""]
        for i, layer in enumerate(layers):
            if i == 0:
                c = center[layer[0]]
                lines += [" " * c + "●", " " * c + "│"]
            lines += list(boxes[i])
            arrows = ""
            for src in layer:
                for event, tgt in tree.get(src, []):
                    c = center[tgt]
                    lines.append(" " * c + "│ " + event)
                    arrows += " " * (c - len(arrows)) + "▼"
            if arrows:
                lines.append(arrows)
            for name in layer:
                if name not in self._transitions:  # terminal
                    c = center[name]
                    lines += [" " * c + "│", " " * c + "◉"]
        if extra:
            lines += ["", "edges not drawn:"] + extra
        wildcard = self._transitions.get(_ANY, {})
        if wildcard:
            lines.append("any state:" if extra else "\nany state:")
            for event, goto in wildcard.items():
                lines.append(f"\t{_ANY} --{event}--> {goto.__name__}")
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
        return StateNode(fn, self._transitions, self._error_routes, self._initial)

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
        node = StateNode(
            initial, self._transitions, self._error_routes, initial.__name__
        )
        node._enter("")
        return node
