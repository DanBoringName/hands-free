"""The `hands-free` command.

Each subcommand is a parser and a handler. The handler takes the parsed arguments and
returns the exit status, so a new subcommand adds a parser here and leaves the others
alone.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from hands_free import kill_test, murmur


def main(argv: Sequence[str] | None = None) -> int:
    """Run the subcommand `argv` names.

    Args:
        argv: the arguments after the program name, or `None` for the real ones.

    Returns:
        The exit status.
    """
    parser = argparse.ArgumentParser(
        prog="hands-free",
        description="Hands-free voice for a fleet of Claude Code sessions.",
    )
    commands = parser.add_subparsers(required=True, metavar="command")

    room = commands.add_parser(
        "murmur",
        help="run the room in the foreground",
        description="Run Murmur from the tracked config, in the foreground.",
    )
    room.set_defaults(handler=_murmur)

    test = commands.add_parser(
        "kill-test",
        help="judge a Phase 0 kill-test run",
        description=(
            "Judge a Phase 0 kill-test run from its recording and Murmur's log, and "
            "write a Markdown report. Exits 0 when every check passes."
        ),
    )
    test.add_argument(
        "recording",
        type=Path,
        help="the phone's WAV file, from the Mumble client's per-user recording",
    )
    test.add_argument(
        "--user", required=True, help="the name the phone joined the room with"
    )
    test.add_argument(
        "--database",
        type=Path,
        help="Murmur's database (default: the one `hands-free murmur` runs with)",
    )
    test.add_argument(
        "--start",
        type=datetime.fromisoformat,
        help=(
            "when the recording started, as an ISO time, local unless it carries an "
            "offset (default: the file's modification time less its length)"
        ),
    )
    test.add_argument(
        "--shortest-gap",
        type=float,
        default=kill_test.SHORTEST_GAP,
        help=(
            "the shortest digital silence to report, in seconds (default: %(default)s)"
        ),
    )
    test.set_defaults(handler=_kill_test)

    arguments = parser.parse_args(argv)
    return arguments.handler(arguments)


def _murmur(_: argparse.Namespace) -> int:
    """`hands-free murmur`."""
    return murmur.run(murmur.Layout.from_environment())


def _kill_test(arguments: argparse.Namespace) -> int:
    """`hands-free kill-test`."""
    database = arguments.database or murmur.Layout.from_environment().database
    return kill_test.run(
        arguments.recording,
        user=arguments.user,
        database=database,
        start=arguments.start,
        shortest_gap=arguments.shortest_gap,
    )
