"""The `hands-free` command, end to end."""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
from support import RATE, noise, write_wav

from hands_free import cli, murmur
from hands_free.kill_test.checks import Outcome, Verdict
from hands_free.kill_test.recording import Gap
from hands_free.kill_test.report import GAPS_LISTED, Findings, render

# The phone joins at 22:29, the recording runs 22:30:00 to 22:30:30, and the phone
# leaves at 22:35.
STAYED = (
    ("2026-11-04 22:29:00", "<1:phone(-1)> Authenticated"),
    ("2026-11-04 22:35:00", "<1:phone(-1)> Connection closed: gone [1]"),
)
DROPPED = (
    ("2026-11-04 22:29:00", "<1:phone(-1)> Authenticated"),
    ("2026-11-04 22:30:12", "<1:phone(-1)> Timeout"),
    ("2026-11-04 22:30:12", "<1:phone(-1)> Connection closed:  [-1]"),
    ("2026-11-04 22:30:20", "<2:phone(-1)> Authenticated"),
)
START = "2026-11-04T22:30:00+00:00"


def headset(seconds: float = 30.0) -> np.ndarray:
    return noise(seconds, cutoff=7900.0)


def kill_test(*arguments: str) -> int:
    return cli.main(["kill-test", *arguments])


def test_a_clean_run_passes_every_check(
    tmp_path: Path, murmur_log: Callable[..., Path], capsys: pytest.CaptureFixture[str]
):
    wav = write_wav(tmp_path / "phone.wav", headset())
    database = murmur_log(STAYED)
    status = kill_test(
        str(wav), "--user", "phone", "--database", str(database), "--start", START
    )
    report = capsys.readouterr().out
    assert status == 0
    assert report.startswith(
        "`phone.wav` is 0 min 30 s at 48 kHz, from 22:30:00 to 22:30:30 UTC on "
        "2026-11-04. The start was given."
    )
    assert (
        "| Nothing dropped | pass | One connection, from 22:29:00 to 22:35:00" in report
    )
    assert "| Audio arrived continuously | pass |" in report
    assert "| The headset mic was in use | pass |" in report
    assert "Bluetooth HFP wideband (mSBC)" in report
    assert "- From 22:29:00 to 22:35:00 UTC, ended: gone." in report


def test_a_dropped_run_fails_and_shows_where(
    tmp_path: Path, murmur_log: Callable[..., Path], capsys: pytest.CaptureFixture[str]
):
    samples = headset()
    samples[12 * RATE : 20 * RATE] = 0
    wav = write_wav(tmp_path / "phone.wav", samples)
    database = murmur_log(DROPPED)
    status = kill_test(
        str(wav), "--user", "phone", "--database", str(database), "--start", START
    )
    report = capsys.readouterr().out
    assert status == 1
    assert "| Nothing dropped | fail | 2 connections during the recording" in report
    assert "ended: Timeout" in report
    assert "- At 0:12.0 (22:30:12 UTC), 8.0 s." in report


def test_the_phones_own_mic_fails_the_headset_check(
    tmp_path: Path, murmur_log: Callable[..., Path], capsys: pytest.CaptureFixture[str]
):
    wav = write_wav(tmp_path / "phone.wav", noise(30.0))
    database = murmur_log(STAYED)
    status = kill_test(
        str(wav), "--user", "phone", "--database", str(database), "--start", START
    )
    assert status == 1
    assert "| The headset mic was in use | fail |" in capsys.readouterr().out


def test_without_a_start_the_file_time_less_its_length_is_used(
    tmp_path: Path, murmur_log: Callable[..., Path], capsys: pytest.CaptureFixture[str]
):
    wav = write_wav(tmp_path / "phone.wav", headset())
    written = datetime(2026, 11, 4, 22, 30, 30, tzinfo=UTC).timestamp()
    os.utime(wav, (written, written))
    database = murmur_log(STAYED)
    assert kill_test(str(wav), "--user", "phone", "--database", str(database)) == 0
    report = capsys.readouterr().out
    assert "from 22:30:00 to 22:30:30 UTC" in report
    assert (
        "The start is the file's modification time less the recording's length."
        in report
    )


def test_the_default_database_is_the_rooms(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    murmur_log: Callable[..., Path],
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    database = murmur.Layout.from_environment().database
    database.parent.mkdir(parents=True)
    murmur_log(STAYED).rename(database)
    wav = write_wav(tmp_path / "phone.wav", headset())
    assert kill_test(str(wav), "--user", "phone", "--start", START) == 0
    capsys.readouterr()


@pytest.mark.parametrize("problem", ["missing recording", "not a wav", "missing log"])
def test_what_cant_be_read_stops_it_with_a_reason(
    tmp_path: Path,
    murmur_log: Callable[..., Path],
    capsys: pytest.CaptureFixture[str],
    problem: str,
):
    wav = write_wav(tmp_path / "phone.wav", headset(1.0))
    database = murmur_log(STAYED)
    if problem == "missing recording":
        wav = tmp_path / "missing.wav"
    elif problem == "not a wav":
        wav.write_bytes(b"not audio")
    else:
        database = tmp_path / "missing.sqlite"
    status = kill_test(str(wav), "--user", "phone", "--database", str(database))
    captured = capsys.readouterr()
    assert status == 2
    assert captured.out == ""
    assert captured.err.startswith("hands-free kill-test: ")


def test_the_murmur_command_runs_the_room_for_this_user(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    started: list[murmur.Layout] = []
    monkeypatch.setattr(murmur, "run", lambda layout: started.append(layout) or 0)
    assert cli.main(["murmur"]) == 0
    assert started == [murmur.Layout.from_environment()]


def test_a_command_is_required(capsys: pytest.CaptureFixture[str]):
    with pytest.raises(SystemExit) as raised:
        cli.main([])
    assert raised.value.code == 2
    assert "command" in capsys.readouterr().err


def test_a_long_list_of_gaps_is_cut_short():
    findings = Findings(
        recording_name="phone.wav",
        rate=RATE,
        start=datetime(2026, 11, 4, 22, 30, tzinfo=UTC),
        seconds=1800.0,
        start_inferred=False,
        user="phone",
        verdicts=[Verdict("A check", Outcome.FAIL, "a | b")],
        connections=[],
        gaps=[Gap(float(i * 10), 1.0) for i in range(GAPS_LISTED + 3)],
        shortest_gap=0.5,
    )
    report = render(findings)
    assert report.count("\n- At ") == GAPS_LISTED
    assert "- And 3 more.\n" in report
    assert "| A check | fail | a \\| b |" in report
    assert "Connections as `phone` during the recording:\n\n- None.\n" in report
