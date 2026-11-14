"""Core logic for jsonpeel: loading, querying, diffing and rendering JSON.

Zero dependencies, standard library only. The CLI layer lives in cli.py;
everything here is importable and testable on its own.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from typing import Any

from .errors import JsonPeelError

DEFAULT_INDENT = 2
MAX_QUERY_TOKENS = 64  # a path longer than this is almost certainly a paste error

# One escape sequence per token type. Kept deliberately small — this is
# terminal colour, not a syntax highlighting engine.
COLOURS = {
    "key": "\x1b[36m",     # cyan
    "string": "\x1b[32m",  # green
    "number": "\x1b[33m",  # yellow
    "literal": "\x1b[35m",  # magenta, for true / false / null
    "reset": "\x1b[0m",
}

# Tokens inside a json.dumps() string: a quoted string (with escapes),
# a number, or a literal. json.dumps output is well-formed, so a flat
# regex scan is safe here — no hand-rolled JSON parser hiding underneath.
_TOKEN_RE = re.compile(
    r'"(?:\\.|[^"\\])*"|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?|true|false|null'
)


def load_json(text: str, source: str) -> Any:
    """Parse *text* as JSON, raising JsonPeelError with a human message.

    ``source`` is the file name (or "stdin") shown in the error so the
    user knows which input broke.
    """
    if not text.strip():
        raise JsonPeelError(f"{source}: empty input — expected a JSON document")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise JsonPeelError(
            f"{source}: invalid JSON — {exc.msg} "
            f"(line {exc.lineno}, column {exc.colno})"
        ) from exc


def parse_path(path: str) -> list[str | int]:
    """Split a dot-path like ``user.addresses[0].city`` into tokens.

    Keys are strings, ``[n]`` parts are ints. A leading dot and doubled
    dots are tolerated — ``.user.name`` means the same as ``user.name``.
    """
    if not path:
        raise JsonPeelError(
            "empty query path — give something like user.name or items[0].id"
        )
    tokens: list[str | int] = []
    i, n = 0, len(path)
    while i < n:
        char = path[i]
        if char == ".":
            i += 1
            continue
        if char == "[":
            close = path.find("]", i)
            if close == -1:
                raise JsonPeelError(f"bad query path {path!r}: missing ']'")
            raw = path[i + 1 : close]
            if not raw.lstrip("-").isdigit():
                raise JsonPeelError(
                    f"bad query path {path!r}: [{raw}] is not a number"
                )
            tokens.append(int(raw))
            i = close + 1
            continue
        j = i
        while j < n and path[j] not in ".[":
            j += 1
        tokens.append(path[i:j])
        i = j
    if not tokens:
        raise JsonPeelError(f"bad query path {path!r}: nothing to look up")
    if len(tokens) > MAX_QUERY_TOKENS:
        raise JsonPeelError(
            f"bad query path {path!r}: more than {MAX_QUERY_TOKENS} parts"
        )
    return tokens


def _path_so_far(tokens: list[str | int], upto: int) -> str:
    """Rebuild the path prefix up to index *upto* for error messages."""
    out = ""
    for token in tokens[: upto + 1]:
        if isinstance(token, int):
            out += f"[{token}]"
        else:
            out += f".{token}" if out else token
    return out


def get_path(data: Any, path: str) -> Any:
    """Return the value at *path* inside *data*, or raise JsonPeelError."""
    tokens = parse_path(path)
    current = data
    for index, token in enumerate(tokens):
        if isinstance(token, str):
            if not isinstance(current, dict):
                raise JsonPeelError(
                    f"no key {_path_so_far(tokens, index)!r}: "
                    f"{_path_so_far(tokens, index - 1) or 'root'} is not an object"
                )
            if token not in current:
                raise JsonPeelError(f"no such key: {_path_so_far(tokens, index)!r}")
            current = current[token]
        else:
            if not isinstance(current, list):
                raise JsonPeelError(
                    f"no index [{token}]: "
                    f"{_path_so_far(tokens, index - 1) or 'root'} is not an array"
                )
            if token < -len(current) or token >= len(current):
                raise JsonPeelError(
                    f"index [{token}] out of range: "
                    f"{_path_so_far(tokens, index - 1) or 'root'} "
                    f"has {len(current)} item(s)"
                )
            current = current[token]
    return current


def list_paths(data: Any, prefix: str = "") -> list[str]:
    """All leaf paths in *data*, in document order.

    Leaves are scalars and empty containers — ``a.b`` for scalars,
    ``a.items[0]`` for array elements. Handy for exploring a JSON file
    you have never seen before.
    """
    paths: list[str] = []
    if isinstance(data, dict):
        if not data:
            return [prefix] if prefix else []
        for key, value in data.items():
            child = f"{prefix}.{key}" if prefix else key
            paths.extend(list_paths(value, child))
    elif isinstance(data, list):
        if not data:
            return [prefix] if prefix else []
        for i, value in enumerate(data):
            paths.extend(list_paths(value, f"{prefix}[{i}]"))
    else:
        paths.append(prefix)
    return paths


def _show(value: Any) -> str:
    """One-line rendering of a value for diff output."""
    return json.dumps(value, ensure_ascii=False)


def diff_json(left: Any, right: Any, prefix: str = "") -> list[str]:
    """Structural diff between two JSON values, as readable lines.

    ``~ path: old -> new`` for changed values, ``+ path: value`` for
    additions, ``- path: value`` for removals. Keys are walked in sorted
    order so the output is stable run to run.
    """
    lines: list[str] = []
    if isinstance(left, dict) and isinstance(right, dict):
        for key in sorted(set(left) | set(right)):
            child = f"{prefix}.{key}" if prefix else key
            if key not in left:
                lines.append(f"+ {child}: {_show(right[key])}")
            elif key not in right:
                lines.append(f"- {child}: {_show(left[key])}")
            else:
                lines.extend(diff_json(left[key], right[key], child))
    elif isinstance(left, list) and isinstance(right, list):
        for i in range(max(len(left), len(right))):
            child = f"{prefix}[{i}]"
            if i >= len(left):
                lines.append(f"+ {child}: {_show(right[i])}")
            elif i >= len(right):
                lines.append(f"- {child}: {_show(left[i])}")
            else:
                lines.extend(diff_json(left[i], right[i], child))
    elif left != right:
        lines.append(f"~ {prefix or 'root'}: {_show(left)} -> {_show(right)}")
    return lines


def colourise(text: str) -> str:
    """Add ANSI colour to an already-dumped JSON string.

    A string token is a key when the next non-space character is ``:``.
    Everything else passes through untouched.
    """
    out: list[str] = []
    pos = 0
    for match in _TOKEN_RE.finditer(text):
        out.append(text[pos : match.start()])
        token = match.group(0)
        if token.startswith('"'):
            rest = text[match.end() :].lstrip()
            colour = COLOURS["key"] if rest.startswith(":") else COLOURS["string"]
        elif token in ("true", "false", "null"):
            colour = COLOURS["literal"]
        else:
            colour = COLOURS["number"]
        out.append(f"{colour}{token}{COLOURS['reset']}")
        pos = match.end()
    out.append(text[pos:])
    return "".join(out)


def render(
    data: Any,
    *,
    indent: int = DEFAULT_INDENT,
    sort_keys: bool = False,
    compact: bool = False,
    colour: bool = False,
) -> str:
    """Dump *data* as a string, optionally compact and/or coloured."""
    if compact:
        text = json.dumps(
            data, sort_keys=sort_keys, separators=(",", ":"), ensure_ascii=False
        )
    else:
        text = json.dumps(data, indent=indent, sort_keys=sort_keys, ensure_ascii=False)
    return colourise(text) if colour else text


def write_atomic(path: str, text: str) -> None:
    """Write *text* to *path* via a temp file + rename.

    A crash mid-write leaves the old file intact instead of a half
    written one. The temp file sits next to the target so the rename
    stays on the same filesystem.
    """
    directory = os.path.dirname(os.path.abspath(path))
    fd, tmp_path = tempfile.mkstemp(prefix=".jsonpeel-", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
