class SimplestateError(Exception):
    """Base for all simplestate errors."""


class InvalidGraphError(SimplestateError):
    """The machine definition is invalid (raised by build())."""


class UnknownEventError(SimplestateError):
    """The current state has no transition for the event."""


class StaleStateError(SimplestateError):
    """handle() was called on a state node that already transitioned out."""
