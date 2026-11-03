"""What a recording of the room shows about the audio that reached it.

The recording comes from the Mumble desktop client in the room, set to record each user
to a file of their own in WAV. That is one channel of 16-bit PCM at 48 kHz. Where
nothing arrived from the user, the file holds digital silence, exact zeros, which no
microphone produces while transmitting continuously. The protocol's calibration run
checks both of those before a run is judged by them.

The band edge separates the microphones. Bluetooth's hands-free profile carries the
headset mic at 8 kHz (CVSD) or 16 kHz (mSBC), so after the phone resamples it nothing is
left above 4 or 8 kHz, and the level falls off a cliff there. The phone's own mic
reaches the codec at full band, and speech fades out gradually above a few kHz with no
cliff.
"""

from __future__ import annotations

import wave
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt

Samples = npt.NDArray[np.int16]

FRAME_SECONDS = 0.01
"""The resolution of a gap. Mumble's audio packets are 10 to 60 ms."""

WINDOW = 2048
"""Samples in each spectrum window, about 43 ms at 48 kHz."""

BATCH = 512
"""Windows transformed together, which bounds the memory a long recording takes."""

LOUDEST_SHARE = 0.25
"""The share of non-silent windows, the loudest, that the spectrum is averaged over.

Under continuous transmit most windows are the room between words, and only the loudest
carry enough speech to show where the band stops.
"""

EDGE_SIDE_HZ = 500.0
"""The width of the band compared on each side of a candidate edge."""

SHARP_FALL_DB = 20.0
"""How far the level must fall across an edge for it to count as a cut.

The cut a resampler leaves is 40 dB or more. Speech through a muffled mic, such as a
phone in a pocket, fades by a few dB over the same width.
"""

SEARCH_HZ = (3000.0, 18000.0)
"""Where an edge is looked for. Below it is the body of speech, and above it Opus's own
full-band limit at 20 kHz."""


class RecordingError(ValueError):
    """The file is not a recording the kill test can read."""


@dataclass(frozen=True)
class Recording:
    """One channel of 16-bit audio.

    Attributes:
        samples: the audio.
        rate: samples per second.
    """

    samples: Samples
    rate: int

    @property
    def seconds(self) -> float:
        """How long the recording is."""
        return len(self.samples) / self.rate


@dataclass(frozen=True)
class Gap:
    """A stretch of digital silence, where nothing arrived.

    Attributes:
        start: seconds from the start of the recording.
        length: seconds.
    """

    start: float
    length: float


@dataclass(frozen=True)
class Spectrum:
    """The average power spectrum of the loudest part of a recording.

    Attributes:
        frequencies: the centre of each bin, in Hz.
        level_db: the power in each bin, in dB against an arbitrary reference.
        seconds: how much audio it was averaged over.
    """

    frequencies: npt.NDArray[np.float64]
    level_db: npt.NDArray[np.float64]
    seconds: float

    @property
    def top(self) -> float:
        """The highest frequency the recording can show."""
        return float(self.frequencies[-1])


@dataclass(frozen=True)
class BandEdge:
    """Where the level falls off a cliff.

    Attributes:
        frequency: Hz.
        fall_db: how far the level falls across it.
    """

    frequency: float
    fall_db: float


def read_wav(path: Path) -> Recording:
    """Read a recording made by the Mumble desktop client.

    Args:
        path: a WAV file.

    Returns:
        The recording.

    Raises:
        RecordingError: the file is not one channel of 16-bit PCM.
    """
    try:
        with wave.open(str(path), "rb") as file:
            channels, width = file.getnchannels(), file.getsampwidth()
            rate, data = file.getframerate(), file.readframes(file.getnframes())
    except (wave.Error, EOFError) as error:
        msg = f"{path.name} is not a PCM WAV file ({error})"
        raise RecordingError(msg) from error
    if channels != 1 or width != 2:
        msg = (
            f"{path.name} has {channels} channel(s) of {8 * width}-bit audio. The kill "
            f"test reads one channel of 16-bit PCM, which is what the Mumble client "
            f"writes when it records each user to a WAV file of their own."
        )
        raise RecordingError(msg)
    return Recording(np.frombuffer(data, dtype="<i2"), rate)


def silent_gaps(recording: Recording, shortest: float) -> list[Gap]:
    """Every stretch of digital silence at least `shortest` seconds long.

    Args:
        recording: the recording.
        shortest: the shortest gap to report, in seconds.

    Returns:
        The gaps, in order.
    """
    frame = round(recording.rate * FRAME_SECONDS)
    count = len(recording.samples) // frame
    frames = recording.samples[: count * frame].reshape(count, frame)
    silent = ~np.any(frames, axis=1)
    edges = np.diff(np.concatenate(([0], silent.astype(np.int8), [0])))
    starts, ends = np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)
    fewest = round(shortest / FRAME_SECONDS)
    return [
        Gap(start * frame / recording.rate, (end - start) * frame / recording.rate)
        for start, end in zip(starts.tolist(), ends.tolist(), strict=True)
        if end - start >= fewest
    ]


def loud_spectrum(recording: Recording) -> Spectrum | None:
    """The average spectrum of the loudest quarter of the recording's sound.

    Args:
        recording: the recording.

    Returns:
        The spectrum, or `None` when the recording holds no sound at all.
    """
    count = len(recording.samples) // WINDOW
    if count == 0:
        return None
    windows = recording.samples[: count * WINDOW].reshape(count, WINDOW)
    rms = np.concatenate([_rms(batch) for batch in _batches(windows)])
    sounding = rms[rms > 0]
    if sounding.size == 0:
        return None
    threshold = np.quantile(sounding, 1 - LOUDEST_SHARE)
    loud = windows[rms >= threshold]
    taper = np.hanning(WINDOW)
    power = np.zeros(WINDOW // 2 + 1)
    for batch in _batches(loud):
        spectra = np.fft.rfft(batch.astype(np.float64) * taper, axis=1)
        power += np.sum(np.abs(spectra) ** 2, axis=0)
    power /= len(loud)
    return Spectrum(
        frequencies=np.fft.rfftfreq(WINDOW, 1 / recording.rate),
        level_db=10 * np.log10(power + np.finfo(np.float64).tiny),
        seconds=len(loud) * WINDOW / recording.rate,
    )


def band_edge(spectrum: Spectrum) -> BandEdge | None:
    """The sharpest fall in level within `SEARCH_HZ`, if it is sharp enough to be a cut.

    Each candidate frequency compares the mean level of the `EDGE_SIDE_HZ` below it
    with the mean of the same width above it.

    Args:
        spectrum: the recording's spectrum.

    Returns:
        The edge, or `None` when nothing falls by `SHARP_FALL_DB`.
    """
    bin_hz = float(spectrum.frequencies[1] - spectrum.frequencies[0])
    side = max(1, round(EDGE_SIDE_HZ / bin_hz))
    level = spectrum.level_db
    lowest = max(side, int(np.searchsorted(spectrum.frequencies, SEARCH_HZ[0])))
    highest = min(
        len(level) - side, int(np.searchsorted(spectrum.frequencies, SEARCH_HZ[1]))
    )
    if lowest >= highest:
        return None
    running = np.concatenate(([0.0], np.cumsum(level)))
    candidates = np.arange(lowest, highest)
    below = (running[candidates] - running[candidates - side]) / side
    above = (running[candidates + side] - running[candidates]) / side
    falls = below - above
    sharpest = int(np.argmax(falls))
    if falls[sharpest] < SHARP_FALL_DB:
        return None
    return BandEdge(
        frequency=float(spectrum.frequencies[candidates[sharpest]]),
        fall_db=float(falls[sharpest]),
    )


def _batches(windows: Samples) -> Iterator[Samples]:
    """`windows` in groups of `BATCH` rows."""
    for first in range(0, len(windows), BATCH):
        yield windows[first : first + BATCH]


def _rms(windows: Samples) -> npt.NDArray[np.float64]:
    """The root mean square of each row."""
    return np.sqrt(np.mean(windows.astype(np.float64) ** 2, axis=1))
