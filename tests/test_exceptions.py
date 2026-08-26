from simplestate.exceptions import (
    SimplestateError,
    InvalidGraphError,
    UnknownEventError,
    StaleStateError,
)


def test_exception_hierarchy():
    assert issubclass(InvalidGraphError, SimplestateError)
    assert issubclass(UnknownEventError, SimplestateError)
    assert issubclass(StaleStateError, SimplestateError)
    assert issubclass(SimplestateError, Exception)
