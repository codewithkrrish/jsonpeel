"""Thin CLI over jsonpeel.core — argument parsing and exit codes only.

Exit codes: 0 ok, 1 a runtime problem (bad JSON, missing key, files
differ in --diff mode), 2 a usage error from argparse.
"""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .core import (
    DEFAULT_INDENT,
    diff_json,
    get_path,
    list_paths,
    load_json,
    render,
    write_atomic,
)
from .errors import JsonPeelError

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_DIFFERS = 1  # --diff prints the differences and exits 1, like diff(1)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jsonpeel",
        description="Peek inside JSON: pretty-print it, pull out one value "
        "by dot-path, or diff two files.",
    )
    parser.add_argument(
        "file",
        nargs="?",
        help="JSON file to read (default: stdin; use - for stdin explicitly)",
    )
    parser.add_argument(
        "-q",
        "--query",
        metavar="PATH",
        help="dot-path to print instead of the whole document, e.g. user.name or items[0].id",
    )
    parser.add_argument(
        "--keys",
        action="store_true",
        help="list every leaf path in the document, one per line",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="only check the JSON is valid, print nothing on success",
    )
    parser.add_argument(
        "--diff",
        metavar="OTHER",
        help="compare FILE against OTHER and show added/removed/changed values",
    )
    parser.add_argument(
        "--indent",
        type=int,
        default=DEFAULT_INDENT,
        metavar="N",
        help=f"spaces per level (default {DEFAULT_INDENT})",
    )
    parser.add_argument(
        "--sort-keys",
        action="store_true",
        help="sort object keys alphabetically",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="minified single-line output instead of pretty-printed",
    )
    parser.add_argument(
        "--color",
        choices=["auto", "always", "never"],
        default="auto",
        help="colour the output: auto (only on a terminal), always, never",
    )
    parser.add_argument(
        "-o",
        "--output",
        metavar="FILE",
        help="write the result to FILE instead of stdout",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite FILE given with -o if it already exists",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="with -o: show what would be written, write nothing",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


def _read_input(path: str | None) -> tuple[str, str]:
    """Read the main input. Returns (text, display name for errors)."""
    if path is None or path == "-":
        if path is None and sys.stdin.isatty():
            raise JsonPeelError(
                "no input: give a file, or pipe JSON in "
                "(e.g. curl -s https://api.example.com | jsonpeel)"
            )
        return sys.stdin.read(), "stdin"
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read(), path
    except OSError as exc:
        raise JsonPeelError(f"cannot read {path}: {exc.strerror}") from exc


def _read_file(path: str) -> tuple[str, str]:
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read(), path
    except OSError as exc:
        raise JsonPeelError(f"cannot read {path}: {exc.strerror}") from exc


def _emit(text: str, args: argparse.Namespace) -> int:
    """Send *text* to stdout or to -o, honouring --force / --dry-run."""
    if args.output is None:
        print(text)
        return EXIT_OK
    if args.dry_run:
        print(text)
        print(
            f"jsonpeel: dry run — {args.output} untouched",
            file=sys.stderr,
        )
        return EXIT_OK
    import os

    if os.path.exists(args.output) and not args.force:
        raise JsonPeelError(
            f"{args.output} already exists — pass --force to overwrite it"
        )
    try:
        write_atomic(args.output, text + "\n")
    except OSError as exc:
        raise JsonPeelError(
            f"cannot write {args.output}: {exc.strerror}"
        ) from exc
    return EXIT_OK


def run(args: argparse.Namespace) -> int:
    if args.indent < 0:
        raise JsonPeelError("--indent must be 0 or more")
    if args.diff and (args.query or args.keys or args.validate):
        raise JsonPeelError("--diff cannot be combined with --query, --keys or --validate")
    if args.query and args.keys:
        raise JsonPeelError("--query and --keys do not mix — pick one")

    text, source = _read_input(args.file)
    data = load_json(text, source)

    if args.validate:
        print(f"{source}: valid JSON", file=sys.stderr)
        return EXIT_OK

    # Colour only reaches a terminal; files always get plain text.
    use_colour = (
        args.color == "always"
        or (args.color == "auto" and sys.stdout.isatty() and args.output is None)
    )

    if args.diff:
        other_text, other_source = _read_file(args.diff)
        other = load_json(other_text, other_source)
        lines = diff_json(data, other)
        if not lines:
            print("identical", file=sys.stderr)
            return EXIT_OK
        return _emit("\n".join(lines), args) or EXIT_DIFFERS

    if args.keys:
        return _emit("\n".join(list_paths(data)), args)

    picked = get_path(data, args.query) if args.query else data
    return _emit(
        render(
            picked,
            indent=args.indent,
            sort_keys=args.sort_keys,
            compact=args.compact,
            colour=use_colour,
        ),
        args,
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return run(args)
    except JsonPeelError as exc:
        print(f"jsonpeel: {exc}", file=sys.stderr)
        return EXIT_ERROR
    except BrokenPipeError:
        # Piping into `head` closes stdout early; dying quietly with the
        # usual exit code is the polite thing, not a traceback.
        try:
            sys.stdout.close()
        except BrokenPipeError:
            pass
        return EXIT_OK
