"""Entry point for `python -m jsonpeel`."""

import sys

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
