"""The three checks, judged from what a run left behind."""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pytest

from hands_free.kill_test.checks import (
    CONTINUOUS,
    HEADSET,
    NOTHING_DROPPED,
    Outcome,
    clock,
    counted,
    judge_band,
    judge_connections,
    judge_gaps,
    offset,
)
from hands_free.kill_test.connections import Connection
from hands_free.kill_test.recording import BandEdge, Gap, Spectrum

START = datetime(2026, 11, 4, 22, 30, tzinfo=UTC)
END = datetime(2026, 11, 4, 23, 0, tzinfo=UTC)


def at(minute: int, hour: int = 22) -> datetime:
    return datetime(2026, 11, 4, hour, minute, tzinfo=UTC)


def full_spectrum(seconds: float = 60.0, top: float = 24000.0) -> Spectrum:
    frequencies = np.linspace(0, top, 1025)
    return Spectrum(frequencies, np.zeros_like(frequencies), seconds)


def test_one_connection_across_the_whole_recording_passes():
    verdict = judge_connections([Connection("phone", 1, at(29))], START, END)
    assert (verdict.check, verdict.outcome) == (NOTHING_DROPPED, Outcome.PASS)
    assert "still open" in verdict.detail


def test_a_connection_that_closed_after_the_recording_passes():
    connection = Connection("phone", 1, at(29), at(5, hour=23), "gone")
    assert judge_connections([connection], START, END).outcome is Outcome.PASS


def test_a_drop_and_a_reconnect_fails_and_says_why():
    verdict = judge_connections(
        [
            Connection("phone", 1, at(29), at(41), "Timeout"),
            Connection("phone", 2, at(42)),
        ],
        START,
        END,
    )
    assert verdict.outcome is Outcome.FAIL
    assert verdict.detail.startswith("2 connections during the recording")
    assert "to 22:41:00 UTC, ended: Timeout" in verdict.detail


def test_joining_after_the_recording_started_fails():
    verdict = judge_connections([Connection("phone", 1, at(31))], START, END)
    assert verdict.outcome is Outcome.FAIL
    assert verdict.detail.startswith("One connection during the recording")


def test_no_connection_at_all_fails():
    earlier = Connection("phone", 1, at(0), at(10), "gone")
    verdict = judge_connections([earlier], START, END)
    assert verdict.outcome is Outcome.FAIL
    assert "No connection" in verdict.detail


def test_no_gaps_passes():
    verdict = judge_gaps([], 0.5)
    assert (verdict.check, verdict.outcome) == (CONTINUOUS, Outcome.PASS)
    assert "0.5 s" in verdict.detail


def test_gaps_fail_with_the_longest_named():
    verdict = judge_gaps([Gap(61.0, 0.7), Gap(723.25, 4.1)], 0.5)
    assert verdict.outcome is Outcome.FAIL
    assert verdict.detail == "2 gaps, 4.8 s in all. The longest is 4.1 s, at 12:03.2."


@pytest.mark.parametrize(
    ("frequency", "codec"),
    [(3950.0, "CVSD"), (4300.0, "CVSD"), (7700.0, "mSBC"), (8000.0, "mSBC")],
)
def test_an_hfp_cut_passes_and_names_the_codec(frequency: float, codec: str):
    verdict = judge_band(full_spectrum(), BandEdge(frequency, 60.0))
    assert (verdict.check, verdict.outcome) == (HEADSET, Outcome.PASS)
    assert codec in verdict.detail


def test_no_cut_is_the_phones_own_mic():
    verdict = judge_band(full_spectrum(), None)
    assert verdict.outcome is Outcome.FAIL
    assert "phone's own mic" in verdict.detail


@pytest.mark.parametrize("frequency", [5500.0, 12000.0, 16000.0])
def test_a_cut_no_hfp_codec_makes_is_unsure(frequency: float):
    verdict = judge_band(full_spectrum(), BandEdge(frequency, 60.0))
    assert verdict.outcome is Outcome.UNSURE
    assert "matches neither HFP codec" in verdict.detail


@pytest.mark.parametrize("spectrum", [None, full_spectrum(seconds=2.0)])
def test_too_little_sound_is_unsure(spectrum: Spectrum | None):
    verdict = judge_band(spectrum, None)
    assert verdict.outcome is Outcome.UNSURE
    assert "Too little sound" in verdict.detail


def test_a_recording_too_narrow_to_show_the_cuts_is_unsure():
    verdict = judge_band(full_spectrum(top=8000.0), None)
    assert verdict.outcome is Outcome.UNSURE
    assert "8 kHz" in verdict.detail


@pytest.mark.parametrize(
    ("seconds", "text"),
    [(0.0, "0:00.0"), (59.96, "1:00.0"), (723.25, "12:03.2"), (3600.0, "60:00.0")],
)
def test_an_offset_reads_as_minutes_and_seconds(seconds: float, text: str):
    assert offset(seconds) == text


def test_counts_and_clocks_read_as_words():
    assert counted(1, "gap") == "One gap"
    assert counted(3, "gap") == "3 gaps"
    assert clock(at(5, hour=9)) == "09:05:00"
