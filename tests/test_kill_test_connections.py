"""The phone's connections, read from Murmur's log."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
from support import JOINED_AND_LEFT, TIMED_OUT, WRONG_PASSWORD

from hands_free.kill_test.connections import (
    SERVER_STOPPED,
    Connection,
    LogLine,
    connections,
    read_log,
)


def at(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


def lines(*rows: tuple[str, str]) -> list[LogLine]:
    return [LogLine(at(time), message) for time, message in rows]


def test_a_connection_runs_from_admission_to_close():
    assert connections(lines(*JOINED_AND_LEFT), "phone") == [
        Connection(
            "phone",
            1,
            at("2026-11-03 22:18:39"),
            at("2026-11-03 22:18:40"),
            "The remote host closed the connection",
        )
    ]


def test_a_wrong_password_is_not_a_connection():
    assert connections(lines(*WRONG_PASSWORD), "phone") == []


def test_a_timeout_is_why_the_connection_ended():
    [connection] = connections(lines(*TIMED_OUT), "phone")
    assert connection.reason == "Timeout"
    assert connection.ended == at("2026-11-03 22:20:12")


def test_a_connection_still_open_has_no_end():
    [connection] = connections(lines(TIMED_OUT[0]), "phone")
    assert connection.ended is None
    assert connection.reason is None


def test_a_close_with_no_reason_says_so():
    [connection] = connections(
        lines(
            TIMED_OUT[0],
            ("2026-11-03 22:21:00", "<1:phone(-1)> Connection closed:  [-1]"),
        ),
        "phone",
    )
    assert connection.reason == "closed with no reason given"


def test_the_server_stopping_ends_every_connection_and_frees_the_numbers():
    found = connections(
        lines(
            ("2026-11-03 22:00:00", "<1:phone(-1)> Authenticated"),
            ("2026-11-03 22:10:00", "Stopped"),
            ("2026-11-03 22:11:00", "<1:phone(-1)> Authenticated"),
        ),
        "phone",
    )
    assert [(c.started, c.ended, c.reason) for c in found] == [
        (at("2026-11-03 22:00:00"), at("2026-11-03 22:10:00"), SERVER_STOPPED),
        (at("2026-11-03 22:11:00"), None, None),
    ]


@pytest.mark.parametrize("other", ["laptop", "phone2", "Phone"])
def test_only_the_named_user_counts(other: str):
    rows = [
        (time, message.replace("phone", other)) for time, message in JOINED_AND_LEFT
    ]
    assert connections(lines(*rows), "phone") == []


def test_a_name_with_brackets_in_it_is_read_whole():
    rows = [
        (time, message.replace(":phone(", ":phone (S22)("))
        for time, message in TIMED_OUT
    ]
    [connection] = connections(lines(*rows), "phone (S22)")
    assert connection.reason == "Timeout"


def test_other_news_about_an_open_connection_leaves_it_open():
    [connection] = connections(
        lines(TIMED_OUT[0], ("2026-11-03 22:19:30", "<1:phone(-1)> Moved to Root")),
        "phone",
    )
    assert connection.ended is None


def test_connections_come_back_in_the_order_they_started():
    found = connections(
        lines(
            ("2026-11-03 22:00:00", "<1:phone(-1)> Authenticated"),
            ("2026-11-03 22:01:00", "<2:phone(-1)> Authenticated"),
            ("2026-11-03 22:02:00", "<2:phone(-1)> Connection closed: gone [1]"),
        ),
        "phone",
    )
    assert [c.session for c in found] == [1, 2]


def test_the_log_is_read_in_order_and_in_utc(murmur_log: Callable[..., Path]):
    database = murmur_log(JOINED_AND_LEFT)
    log = read_log(database)
    assert [line.message for line in log] == [m for _, m in JOINED_AND_LEFT]
    assert log[0].time == datetime(2026, 11, 3, 22, 18, 39, tzinfo=UTC)


def test_only_the_rooms_server_is_read(murmur_log: Callable[..., Path]):
    murmur_log(JOINED_AND_LEFT)
    database = murmur_log(TIMED_OUT, server_id=2)
    assert len(read_log(database)) == len(JOINED_AND_LEFT)


def test_a_missing_database_is_an_error(tmp_path: Path):
    with pytest.raises(sqlite3.Error):
        read_log(tmp_path / "missing.sqlite")


@pytest.mark.parametrize(
    ("start", "end", "covers", "overlaps"),
    [
        ("22:00", "22:30", True, True),
        ("21:59", "22:30", False, True),
        ("22:00", "22:31", False, True),
        ("22:31", "22:40", False, False),
        ("21:00", "21:59", False, False),
    ],
)
def test_covering_and_overlapping_a_span(
    start: str, end: str, covers: bool, overlaps: bool
):
    connection = Connection("phone", 1, at("2026-11-03 22:00"), at("2026-11-03 22:30"))
    span = at(f"2026-11-03 {start}"), at(f"2026-11-03 {end}")
    assert connection.covers(*span) is covers
    assert connection.overlaps(*span) is overlaps
