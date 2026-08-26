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
