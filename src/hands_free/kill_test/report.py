"""The kill test's findings as Markdown, to paste under a run in the research record.

The report names the recording by its file name alone. Its folder is often a Windows
user folder, which the repository refuses.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from hands_free.kill_test.checks import Verdict, clock, describe, offset
from hands_free.kill_test.connections import Connection
from hands_free.kill_test.recording import Gap

GAPS_LISTED = 20
"""How many gaps to list before saying how many more there were."""


@dataclass(frozen=True)
class Findings:
    """Everything a report says about one run.

    Attributes:
        recording_name: the recording's file name.
        rate: its sample rate.
        start: when it started, in UTC.
        seconds: how long it is.
        start_inferred: whether `start` came from the file's time rather than being
            given.
        user: the name the phone joined with.
        verdicts: the three checks.
        connections: the phone's connections that overlap the recording.
        gaps: the recording's gaps.
        shortest_gap: the shortest gap that was looked for, in seconds.
    """

    recording_name: str
    rate: int
    start: datetime
    seconds: float
    start_inferred: bool
    user: str
    verdicts: Sequence[Verdict]
    connections: Sequence[Connection]
    gaps: Sequence[Gap]
    shortest_gap: float


def render(findings: Findings) -> str:
    """The report.

    Args:
        findings: what the run left behind, judged.

    Returns:
        Markdown that passes the repository's markdownlint rules.
    """
    end = findings.start + timedelta(seconds=findings.seconds)
    minutes, seconds = divmod(round(findings.seconds), 60)
    source = (
        "The start is the file's modification time less the recording's length."
        if findings.start_inferred
        else "The start was given."
    )
    lines = [
        f"`{findings.recording_name}` is {minutes} min {seconds} s at "
        f"{findings.rate / 1000:g} kHz, from {clock(findings.start)} to {clock(end)} "
        f"UTC on {findings.start:%Y-%m-%d}. {source}",
        "",
        "| Check | Result | Evidence |",
        "| --- | --- | --- |",
        *(
            f"| {v.check} | {v.outcome} | {_cell(v.detail)} |"
            for v in findings.verdicts
        ),
        "",
        f"Connections as `{findings.user}` during the recording:",
        "",
        *(f"- {_sentence(describe(c))}." for c in findings.connections),
        *(["- None."] if not findings.connections else []),
        "",
        f"Gaps of {findings.shortest_gap:g} s or more:",
        "",
        *(_gap(findings.start, gap) for gap in findings.gaps[:GAPS_LISTED]),
        *(["- None."] if not findings.gaps else []),
    ]
    hidden = len(findings.gaps) - GAPS_LISTED
    if hidden > 0:
        lines.append(f"- And {hidden} more.")
    return "\n".join(lines) + "\n"


def _gap(start: datetime, gap: Gap) -> str:
    """One gap as a list item, with its time of day."""
    at = start + timedelta(seconds=gap.start)
    return f"- At {offset(gap.start)} ({clock(at)} UTC), {gap.length:.1f} s."


def _sentence(text: str) -> str:
    """`text` with its first letter made a capital."""
    return text[:1].upper() + text[1:]


def _cell(text: str) -> str:
    """`text` made safe for a table cell."""
    return text.replace("|", "\\|")
