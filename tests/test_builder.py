import pytest

from simplestate import StateMachineBuilder
from simplestate.exceptions import (
    InvalidGraphError,
    StaleStateError,
    UnknownEventError,
)


def test_build_returns_initial_node_and_runs_enter():
    entered = []

    def idle(prev, **ctx):
        entered.append(prev)

    state = StateMachineBuilder(idle).build(initial=idle)

    assert state.value == "idle"
    assert str(state) == "idle"
    assert entered == [""]  # enter ran once, prev is "" for the initial entry


def test_handle_returns_next_node():
    log = []

    def idle(prev, **ctx):
        log.append(("idle", prev))

    def uploading(prev, **ctx):
        log.append(("uploading", prev))

    state = (
        StateMachineBuilder(idle, uploading)
        .at(idle).on("upload", goto=uploading)
        .build(initial=idle)
    )

    next_state = state.handle("upload")

    assert next_state is not state
    assert next_state.value == "uploading"
    assert log == [("idle", ""), ("uploading", "idle")]


def test_generator_state_runs_exit_on_transition_out():
    log = []

    def uploading(prev, **ctx):
        log.append("enter")
        nxt = yield
        log.append(f"exit -> {nxt}")

    def done(prev, **ctx):
        log.append("done")

    state = (
        StateMachineBuilder(uploading, done)
        .at(uploading).on("ok", goto=done)
        .build(initial=uploading)
    )
    assert log == ["enter"]  # ran up to yield only

    state.handle("ok")
    assert log == ["enter", "exit -> done", "done"]  # exit before next enter


def test_unhandled_event_raises_unknown_event_error():
    def idle(prev, **ctx): ...

    state = StateMachineBuilder(idle).build(initial=idle)

    with pytest.raises(UnknownEventError, match="idle.*nope"):
        state.handle("nope")


def test_at_any_wildcard_with_state_priority():
    def idle(prev, **ctx): ...
    def uploading(prev, **ctx): ...
    def paused(prev, **ctx): ...

    state = (
        StateMachineBuilder(idle, uploading, paused)
        .at(idle).on("upload", goto=uploading)
        .at(uploading).on("cancel", goto=paused)  # state-specific beats wildcard
        .at_any().on("cancel", goto=idle)
        .build(initial=idle)
    )

    state = state.handle("upload")
    assert state.handle("cancel").value == "paused"  # specific wins

    state = StateMachineBuilder(idle, uploading, paused) \
        .at(idle).on("upload", goto=uploading) \
        .at_any().on("cancel", goto=idle) \
        .build(initial=idle) \
        .handle("upload")
    assert state.handle("cancel").value == "idle"  # wildcard applies


def test_stale_node_raises():
    def idle(prev, **ctx): ...
    def done(prev, **ctx): ...

    state = (
        StateMachineBuilder(idle, done)
        .at(idle).on("finish", goto=done)
        .at(done).on("reset", goto=idle)
        .build(initial=idle)
    )

    state.handle("finish")  # `state` has now transitioned out

    with pytest.raises(StaleStateError, match="idle"):
        state.handle("finish")


def test_build_rejects_unknown_initial():
    def idle(prev, **ctx): ...
    def stranger(prev, **ctx): ...

    with pytest.raises(InvalidGraphError, match="stranger"):
        StateMachineBuilder(idle).build(initial=stranger)


def test_goto_targets_are_auto_registered():
    def idle(prev, **ctx): ...
    def uploading(prev, **ctx): ...

    # uploading not in constructor, but referenced via goto — valid as initial
    state = (
        StateMachineBuilder(idle)
        .at(idle).on("upload", goto=uploading)
        .build(initial=uploading)
    )
    assert state.value == "uploading"


def test_on_error_routes_exception_from_state_function():
    def idle(prev, **ctx): ...

    def uploading(prev, **ctx):
        raise TimeoutError("upload timed out")

    def failed(prev, error, **ctx):
        assert isinstance(error, TimeoutError)

    state = (
        StateMachineBuilder(idle, uploading, failed)
        .at(idle).on("upload", goto=uploading)
        .at(failed).on("retry", goto=uploading)
        .on_error(TimeoutError, goto=failed)
        .build(initial=idle)
    )

    state = state.handle("upload")  # uploading raises -> routed, not raised
    assert state.value == "failed"


def test_unregistered_exception_propagates():
    def idle(prev, **ctx): ...

    def uploading(prev, **ctx):
        raise ValueError("boom")

    state = (
        StateMachineBuilder(idle, uploading)
        .at(idle).on("upload", goto=uploading)
        .on_error(TimeoutError, goto=idle)
        .build(initial=idle)
    )

    with pytest.raises(ValueError, match="boom"):
        state.handle("upload")


def test_on_error_accepts_union():
    def idle(prev, **ctx): ...

    def uploading(prev, **ctx):
        raise ConnectionError("net down")

    def failed(prev, error, **ctx): ...

    state = (
        StateMachineBuilder(idle, uploading, failed)
        .at(idle).on("upload", goto=uploading)
        .on_error(TimeoutError | ConnectionError, goto=failed)
        .build(initial=idle)
    )

    assert state.handle("upload").value == "failed"


def test_on_error_routes_unknown_event():
    def idle(prev, **ctx): ...
    def lost(prev, error, **ctx): ...

    state = (
        StateMachineBuilder(idle, lost)
        .on_error(UnknownEventError, goto=lost)
        .build(initial=idle)
    )

    assert state.handle("nonsense").value == "lost"


def test_exception_in_error_state_propagates_no_recursion():
    def idle(prev, **ctx): ...

    def uploading(prev, **ctx):
        raise TimeoutError("first")

    def failed(prev, error, **ctx):
        raise TimeoutError("second")  # registered type, but must NOT re-route

    state = (
        StateMachineBuilder(idle, uploading, failed)
        .at(idle).on("upload", goto=uploading)
        .on_error(TimeoutError, goto=failed)
        .build(initial=idle)
    )

    with pytest.raises(TimeoutError, match="second"):
        state.handle("upload")


def test_context_is_forwarded_to_enter():
    seen = {}

    def idle(prev, **ctx): ...

    def failed(prev, reason, attempt):
        seen.update(reason=reason, attempt=attempt)

    state = (
        StateMachineBuilder(idle, failed)
        .at(idle).on("error", goto=failed)
        .build(initial=idle)
    )

    state.handle("error", reason="timeout", attempt=3)
    assert seen == {"reason": "timeout", "attempt": 3}


def test_generator_is_fresh_per_visit():
    visits = []

    def working(prev, **ctx):
        local = len(visits)  # captured at enter
        visits.append("enter")
        yield
        visits.append(f"exit-{local}")

    def rest(prev, **ctx): ...

    state = (
        StateMachineBuilder(working, rest)
        .at(working).on("pause", goto=rest)
        .at(rest).on("resume", goto=working)
        .build(initial=working)
    )

    state = state.handle("pause").handle("resume").handle("pause")
    assert visits == ["enter", "exit-0", "enter", "exit-2"]


def test_on_before_at_raises():
    def idle(prev, **ctx): ...

    with pytest.raises(InvalidGraphError, match="at\\(\\)"):
        StateMachineBuilder(idle).on("upload", goto=idle)


def test_builder_supports_event_type_subscription():
    from typing import Literal

    def idle(prev, **ctx): ...
    def done(prev, **ctx): ...

    state = (
        StateMachineBuilder[Literal["finish"]](idle, done)
        .at(idle).on("finish", goto=done)
        .build(initial=idle)
    )
    assert state.handle("finish").value == "done"


def test_repr_shows_state_name():
    def idle(prev, **ctx): ...

    state = StateMachineBuilder(idle).build(initial=idle)
    assert repr(state) == "<state: idle>"


def test_generator_return_value_carried_to_next_state():
    def uploading(prev, **ctx):
        yield
        return {"bytes": 42}  # handed to whatever state comes next

    def done(prev, prev_returned, **ctx):
        assert prev_returned == {"bytes": 42}

    state = (
        StateMachineBuilder()
        .at(uploading).on("ok", goto=done)
        .build(initial=uploading)
    )
    assert state.handle("ok").value == "done"


def test_plain_function_return_value_carried_to_next_state():
    def idle(prev, **ctx):
        return "session-token"  # plain state: enter's return is carried on exit

    def working(prev, prev_returned, **ctx):
        assert prev_returned == "session-token"

    state = (
        StateMachineBuilder()
        .at(idle).on("go", goto=working)
        .build(initial=idle)
    )
    assert state.handle("go").value == "working"


def test_no_return_value_means_no_prev_returned_key():
    def idle(prev, **ctx): ...

    def working(prev, **ctx):
        assert "prev_returned" not in ctx

    state = (
        StateMachineBuilder()
        .at(idle).on("go", goto=working)
        .build(initial=idle)
    )
    state.handle("go")


def test_print_graph(capsys):
    def idle(prev, **ctx): ...
    def uploading(prev, **ctx): ...
    def failed(prev, **ctx): ...
    def done(prev, **ctx): ...

    state = (
        StateMachineBuilder(idle)
        .at(idle).on("upload", goto=uploading)
        .at(uploading).on("ok", goto=done).on("error", goto=failed)
        .at(failed).on("retry", goto=uploading)
        .at_any().on("cancel", goto=idle)
        .build(initial=idle)
        .handle("upload")
    )

    state.print_graph()

    assert capsys.readouterr().out == (
        "current: uploading\n"
        "\n"
        "● [idle]\n"
        "  └── upload --> [uploading] *\n"
        "                 ├── ok --> [done] ◉\n"
        "                 └── error --> [failed]\n"
        "                               └── retry --> [uploading] ↺\n"
        "\n"
        "any state:\n"
        "\tcancel --> [idle]\n"
    )
