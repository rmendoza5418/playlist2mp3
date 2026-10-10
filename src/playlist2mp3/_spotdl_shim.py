"""Run spotDL with the auth token read from stdin instead of the command line."""

from __future__ import annotations

import sys
from typing import TextIO


def apply_token(argv: list[str], stream: TextIO) -> list[str]:
    """Return argv plus `--auth-token <line>` if the first stdin line is not empty."""
    token = stream.readline().strip()
    if token:
        return [*argv, "--auth-token", token]
    return list(argv)


def main() -> None:
    from spotdl.console.entry_point import console_entry_point

    sys.argv = apply_token(sys.argv, sys.stdin)
    console_entry_point()


if __name__ == "__main__":
    main()
