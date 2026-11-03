"""The kill test's three checks, each judged from what a run leaves behind.

ADR-2026-11-03-voice-room-switchboard sets them. With the phone locked and pocketed for
30 minutes, nothing may drop when Samsung's sleep timers fire, audio has to arrive
continuously, and the headset mic has to be the one in use.

A check passes, fails, or is unsure when the evidence can't tell. Unsure is not a pass.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from hands_free.kill_test.connections import Connection
from hands_free.kill_test.recording import SEARCH_HZ, BandEdge, Gap, Spectrum

NOTHING_DROPPED = "Nothing dropped"
CONTINUOUS = "Audio arrived continuously"
HEADSET = "The headset mic was in use"

HFP_CUTS = (
    (4000.0, "Bluetooth HFP narrowband (CVSD)"),
    (8000.0, "Bluetooth HFP wideband (mSBC)"),
)
"""Where each hands-free codec leaves the band's edge, and its name."""

CUT_TOLERANCE = 0.15
"""How far, as a share of the frequency, a cut may sit from an HFP codec's and match it.

A resampler's transition band starts a few hundred Hz short of the codec's limit."""

LEAST_SOUND_SECONDS = 5.0
"""The least loud audio the band can be judged on."""


class Outcome(StrEnum):
    """What a check concluded."""

    # A verdict, which bandit takes for a password by its name.
    PASS = "pass"  # noqa: S105
    FAIL = "fail"
    UNSURE = "unsure"


@dataclass(frozen=True)
class Verdict:
    """One check's conclusion and the evidence for it.

    Attributes:
        check: what was asked.
        outcome: the answer.
        detail: the evidence, as a sentence or two.
    """

    check: str
    outcome: Outcome
    detail: str


def judge_connections(
    connections: Sequence[Connection], start: datetime, end: datetime
) -> Verdict:
    """Whether one connection stayed open for the whole recording.

    Args:
        connections: every connection the phone made.
        start: when the recording started.
        end: when it ended.

    Returns:
        The verdict.
    """
    during = [c for c in connections if c.overlaps(start, end)]
    if not during:
        return Verdict(
            NOTHING_DROPPED,
            Outcome.FAIL,
            "No connection under that name overlaps the recording. Check the name, "
            "and the recording's start.",
        )
    spans = "; ".join(describe(c) for c in during)
    if len(during) == 1 and during[0].covers(start, end):
        return Verdict(NOTHING_DROPPED, Outcome.PASS, f"One connection, {spans}.")
    return Verdict(
        NOTHING_DROPPED,
        Outcome.FAIL,
        f"{counted(len(during), 'connection')} during the recording, where one open "
        f"from before its start to after its end was needed: {spans}.",
    )


def judge_gaps(gaps: Sequence[Gap], shortest: float) -> Verdict:
    """Whether any stretch of digital silence broke the audio.

    Args:
        gaps: the recording's gaps.
        shortest: the shortest gap that was looked for, in seconds.

    Returns:
        The verdict.
    """
    if not gaps:
        return Verdict(
            CONTINUOUS,
            Outcome.PASS,
            f"No digital silence of {shortest:g} s or more.",
        )
    longest = max(gaps, key=lambda gap: gap.length)
    total = sum(gap.length for gap in gaps)
    return Verdict(
        CONTINUOUS,
        Outcome.FAIL,
        f"{counted(len(gaps), 'gap')}, {total:.1f} s in all. The longest is "
        f"{longest.length:.1f} s, at {offset(longest.start)}.",
    )


def judge_band(spectrum: Spectrum | None, edge: BandEdge | None) -> Verdict:
    """Whether the band stops where Bluetooth's hands-free profile stops it.

    Args:
        spectrum: the loud audio's spectrum, or `None` when there was no sound.
        edge: the cut found in it, or `None` when there was none.

    Returns:
        The verdict.
    """
    if spectrum is None or spectrum.seconds < LEAST_SOUND_SECONDS:
        return Verdict(HEADSET, Outcome.UNSURE, "Too little sound to judge the band.")
    basis = f"Judged on {spectrum.seconds:.0f} s of the loudest audio."
    if spectrum.top < SEARCH_HZ[1]:
        return Verdict(
            HEADSET,
            Outcome.UNSURE,
            f"The recording holds nothing above {spectrum.top / 1000:g} kHz, too "
            f"little to tell the mics apart. The Mumble client records at 48 kHz.",
        )
    if edge is None:
        return Verdict(
            HEADSET,
            Outcome.FAIL,
            f"No cut between {SEARCH_HZ[0] / 1000:g} and {SEARCH_HZ[1] / 1000:g} kHz, "
            f"so the audio is full band, which is the phone's own mic rather than "
            f"Bluetooth HFP. {basis}",
        )
    found = (
        f"The band stops at {edge.frequency / 1000:.1f} kHz, a {edge.fall_db:.0f} dB"
    )
    for frequency, codec in HFP_CUTS:
        if abs(edge.frequency - frequency) <= CUT_TOLERANCE * frequency:
            return Verdict(HEADSET, Outcome.PASS, f"{found} fall: {codec}. {basis}")
    return Verdict(
        HEADSET,
        Outcome.UNSURE,
        f"{found} fall, which matches neither HFP codec. An Opus bitrate too low for "
        f"full band can cut the band too, which the protocol's calibration rules out. "
        f"{basis}",
    )


def describe(connection: Connection) -> str:
    """A connection's span and how it ended, in a phrase."""
    started = f"from {clock(connection.started)}"
    if connection.ended is None:
        return f"{started} UTC, still open where the log stops"
    return f"{started} to {clock(connection.ended)} UTC, ended: {connection.reason}"


def counted(count: int, noun: str) -> str:
    """`count` of `noun`, in words for one and figures above."""
    return f"One {noun}" if count == 1 else f"{count} {noun}s"


def clock(time: datetime) -> str:
    """A time of day, to the second."""
    return time.strftime("%H:%M:%S")


def offset(seconds: float) -> str:
    """A position in the recording, as minutes and seconds."""
    minutes, rest = divmod(round(seconds, 1), 60)
    return f"{int(minutes)}:{rest:04.1f}"
