"""Errors raised by jsonpeel.

One exception type for everything the user can trigger (bad JSON, a
missing key, a bad query path). The CLI turns these into a plain
one-line message on stderr — no tracebacks for ordinary mistakes.
"""


class JsonPeelError(Exception):
    """A user-facing problem: bad input, a missing key, or a bad flag combo."""
