"""The phone's connections to the room, from Murmur's own log.

Murmur 1.5 keeps its log in its database as well as printing it, in the `slog` table,
with the time each line was written in UTC to the second. A line about a user reads
`<session:name(user id)> text`. The lines this reads were taken from 1.5.517:

- `<1:phone(-1)> Authenticated` opens a connection.
- `<1:phone(-1)> Timeout` comes first when the client went quiet for longer than the
  config's `timeout`, which is how a phone whose app was put to sleep shows up.
- `<1:phone(-1)> Connection closed: <why> [<code>]` ends it.
- `Stopped`, with no user, is the server shutting down, which ends every connection
  without a line of their own.

A wrong password logs a `Connection closed` with no `Authenticated` before it, so a
connection only counts from the line that admits it.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterable
from contextlib import closing
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

SERVER_ID = 1
"""The virtual server a single-room Murmur runs."""

_USER_LINE = re.compile(r"<(?P<session>\d+):(?P<name>.*?)\(-?\d+\)> (?P<text>.*)")
_CLOSED = re.compile(r"Connection closed:\s*(?P<why>.*?)\s*\[-?\d+\]")

TIMED_OUT = "Timeout"
SERVER_STOPPED = "the server stopped"
CLOSED = "closed with no reason given"


@dataclass(frozen=True)
class LogLine:
    """One line of the server's log.

    Attributes:
        time: when Murmur wrote it, in UTC.
        message: the line, without the time.
    """

    time: datetime
    message: str


@dataclass(frozen=True)
class Connection:
    """One stretch of a user being in the room.

    Attributes:
        user: the name the client joined with.
        session: Murmur's number for the connection, unique while the server runs.
        started: when Murmur admitted it.
        ended: when it ended, or `None` if it was still open where the log stops.
        reason: why it ended, in Murmur's words where it gave any.
    """

    user: str
    session: int
    started: datetime
    ended: datetime | None = None
    reason: str | None = None

    def covers(self, start: datetime, end: datetime) -> bool:
        """Whether the connection was open for all of `start` to `end`."""
        return self.started <= start and (self.ended is None or self.ended >= end)

    def overlaps(self, start: datetime, end: datetime) -> bool:
        """Whether the connection was open for any of `start` to `end`."""
        return self.started <= end and (self.ended is None or self.ended >= start)


def read_log(database: Path) -> list[LogLine]:
    """The server's log, oldest line first.

    The database is opened read-only, so this can run while Murmur does.

    Args:
        database: Murmur's SQLite database.

    Returns:
        Every line it holds for the room's server.

    Raises:
        sqlite3.Error: the file is missing or is not Murmur's database.
    """
    uri = f"{database.resolve().as_uri()}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as db:
        rows = db.execute(
            "SELECT msgtime, msg FROM slog WHERE server_id = ? ORDER BY rowid",
            (SERVER_ID,),
        ).fetchall()
    return [
        LogLine(datetime.fromisoformat(time).replace(tzinfo=UTC), message)
        for time, message in rows
    ]


def connections(lines: Iterable[LogLine], user: str) -> list[Connection]:
    """Every connection `user` made, in the order they started.

    Args:
        lines: the server's log, oldest first.
        user: the name the client joins with.

    Returns:
        The connections Murmur admitted, each with how it ended.
    """
    open_now: dict[int, Connection] = {}
    finished: list[Connection] = []
    for line in lines:
        if line.message == "Stopped":
            finished += [
                replace(c, ended=line.time, reason=SERVER_STOPPED)
                for c in open_now.values()
            ]
            open_now.clear()
            continue
        match = _USER_LINE.fullmatch(line.message)
        if match is None or match["name"] != user:
            continue
        session, text = int(match["session"]), match["text"]
        if text == "Authenticated":
            open_now[session] = Connection(user, session, line.time)
        elif session not in open_now:
            continue
        elif text == TIMED_OUT:
            open_now[session] = replace(open_now[session], reason=TIMED_OUT)
        elif closed := _CLOSED.fullmatch(text):
            connection = open_now.pop(session)
            reason = connection.reason or closed["why"] or CLOSED
            finished.append(replace(connection, ended=line.time, reason=reason))
    return sorted([*finished, *open_now.values()], key=lambda c: c.started)
