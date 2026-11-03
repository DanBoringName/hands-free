"""Phase 0's kill test, judged from what a run leaves behind.

A run leaves two things. Murmur's log says when the phone's connection opened and how
it ended, and the Mumble desktop client's recording holds the audio that reached the
room. `run` reads both, judges the three checks ADR-2026-11-03-voice-room-switchboard
sets, and writes a report for `research/phase-0-kill-test.md`.
"""

from __future__ import annotations

import sqlite3
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TextIO

from hands_free.kill_test.checks import (
    Outcome,
    judge_band,
    judge_connections,
    judge_gaps,
)
from hands_free.kill_test.connections import connections, read_log
from hands_free.kill_test.recording import (
    RecordingError,
    band_edge,
    loud_spectrum,
    read_wav,
    silent_gaps,
)
from hands_free.kill_test.report import Findings, render

SHORTEST_GAP = 0.5
"""The shortest digital silence reported as a gap, in seconds.

Shorter losses are covered over by the client's jitter buffer and packet-loss
concealment, so they never reach the recording as silence.
"""


def run(
    recording_path: Path,
    *,
    user: str,
    database: Path,
    start: datetime | None = None,
    shortest_gap: float = SHORTEST_GAP,
    out: TextIO | None = None,
    err: TextIO | None = None,
) -> int:
    """Judge one run and write its report.

    Args:
        recording_path: the phone's recording, from the Mumble desktop client.
        user: the name the phone joined the room with.
        database: Murmur's database, which holds its log.
        start: when the recording started. Without it, the file's modification time
            less the recording's length, since the client writes the file until the
            recording stops.
        shortest_gap: the shortest digital silence to report, in seconds.
        out: where the report goes, standard output unless given.
        err: where a reason to stop goes, standard error unless given.

    Returns:
        0 when every check passes, 1 when any fails or is unsure, and 2 when the
        recording or the log can't be read.
    """
    try:
        recording = read_wav(recording_path)
        log = read_log(database)
    except (RecordingError, sqlite3.Error, OSError) as error:
        (err or sys.stderr).write(f"hands-free kill-test: {error}\n")
        return 2
    inferred = start is None
    if start is None:
        written = datetime.fromtimestamp(recording_path.stat().st_mtime, tz=UTC)
        start = written - timedelta(seconds=recording.seconds)
    start = start.astimezone(UTC)
    end = start + timedelta(seconds=recording.seconds)
    phone = connections(log, user)
    gaps = silent_gaps(recording, shortest_gap)
    spectrum = loud_spectrum(recording)
    verdicts = (
        judge_connections(phone, start, end),
        judge_gaps(gaps, shortest_gap),
        judge_band(spectrum, band_edge(spectrum) if spectrum else None),
    )
    findings = Findings(
        recording_name=recording_path.name,
        rate=recording.rate,
        start=start,
        seconds=recording.seconds,
        start_inferred=inferred,
        user=user,
        verdicts=verdicts,
        connections=[c for c in phone if c.overlaps(start, end)],
        gaps=gaps,
        shortest_gap=shortest_gap,
    )
    (out or sys.stdout).write(render(findings))
    return 0 if all(v.outcome is Outcome.PASS for v in verdicts) else 1
