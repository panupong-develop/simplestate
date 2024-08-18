from simplestate import StateMachine


def test_basic_state():
    m = StateMachine("loading")
    m["loading"] + "error" >> "failed"
    m["loading"] + "ok" >> "success"
    m["?"] + "back" >> "loading"

    m.add_callbacks(
        {
            "loading": lambda previous: print(f"{previous} >> loading"),
            "failed": lambda previous, error: print(f"{previous} >> failed: {error}"),
            "success": lambda previous: print(f"{previous} >> success"),
        }
    )

    # Let's start
    m.start()
    assert m.current == "loading"

    m.handle("error", error="Something went wrong")  # error is a context
    assert m.current == "failed"

    m.handle("back")
    assert m.current == "loading"

    m.handle("ok")
    assert m.current == "success"

    m.handle("back")
    assert m.current == "loading"

    m.handle("back")
    assert m.current == "loading"

    m.handle("ok")
    assert m.current == "success"

    m.handle("ok")
    assert m.current == "success"


def test_traffic_light():
    m = StateMachine("red")
    m["red"] + "next" >> "yellow_green"
    m["yellow_green"] + "next" >> "green"
    m["green"] + "next" >> "yellow_red"
    m["yellow_red"] + "next" >> "red"

    m.start()
    assert m.current == "red"

    m.handle("next")
    assert m.current == "yellow_green"

    m.handle("next")
    assert m.current == "green"

    m.handle("next")
    assert m.current == "yellow_red"

    m.handle("next")
    assert m.current == "red"

    m.handle("next")
    assert m.current == "yellow_green"

    # restart
    m.start(at_state="green")

    m.handle("next")
    assert m.current == "yellow_red"

    m.handle("next")
    assert m.current == "red"

    m.handle("next")
    assert m.current == "yellow_green"
