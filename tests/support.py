"""Synthetic recordings, and log lines a real Murmur wrote, for the tests to share."""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np
import numpy.typing as npt

RATE = 48_000

# The lines Murmur 1.5.517 wrote for a client that joined as `phone` and left, then
# one that gave the wrong password, captured from a real server.
JOINED_AND_LEFT = (
    ("2026-11-03 22:18:39", "<0:(-1)> New connection: 127.0.0.1:48016"),
    ("2026-11-03 22:18:39", "<0:(-1)> Client version 1.4.0 ( : probe)"),
    ("2026-11-03 22:18:39", "Starting voice thread"),
    ("2026-11-03 22:18:39", "<1:phone(-1)> Authenticated"),
    (
        "2026-11-03 22:18:40",
        "<1:phone(-1)> Connection closed: The remote host closed the connection [1]",
    ),
    ("2026-11-03 22:18:40", "Ending voice thread"),
)
WRONG_PASSWORD = (
    ("2026-11-03 22:18:40", "<0:(-1)> New connection: 127.0.0.1:48022"),
    (
        "2026-11-03 22:18:40",
        "<2:phone(-1)> Rejected connection from 127.0.0.1:48022: "
        "Invalid server password",
    ),
    ("2026-11-03 22:18:40", "<2:phone(-1)> Connection closed:  [-1]"),
)
# A client that went quiet until the server's timeout, from the same server.
TIMED_OUT = (
    ("2026-11-03 22:19:29", "<1:phone(-1)> Authenticated"),
    ("2026-11-03 22:20:12", "<1:phone(-1)> Timeout"),
    ("2026-11-03 22:20:12", "<1:phone(-1)> Connection closed:  [-1]"),
)

Samples = npt.NDArray[np.int16]


def noise(seconds: float, cutoff: float | None = None, seed: int = 0) -> Samples:
    """White noise at `RATE`, with nothing above `cutoff` Hz when one is given."""
    rng = np.random.default_rng(seed)
    signal = rng.normal(0, 3000, round(seconds * RATE))
    if cutoff is not None:
        spectrum = np.fft.rfft(signal)
        spectrum[np.fft.rfftfreq(len(signal), 1 / RATE) > cutoff] = 0
        signal = np.fft.irfft(spectrum, len(signal))
    return np.clip(signal, -32767, 32767).astype(np.int16)


def muffled(seconds: float, corner: float = 1500.0) -> Samples:
    """Noise rolled off at 12 dB an octave above `corner`, as fabric over a mic does."""
    rng = np.random.default_rng(1)
    signal = rng.normal(0, 1, round(seconds * RATE))
    spectrum = np.fft.rfft(signal)
    spectrum /= 1 + (np.fft.rfftfreq(len(signal), 1 / RATE) / corner) ** 2
    signal = np.fft.irfft(spectrum, len(signal))
    return (signal / np.abs(signal).max() * 20000).astype(np.int16)


def write_wav(
    path: Path,
    samples: Samples,
    rate: int = RATE,
    channels: int = 1,
    width: int = 2,
) -> Path:
    """Write `samples` as a WAV file and return its path."""
    with wave.open(str(path), "wb") as file:
        file.setnchannels(channels)
        file.setsampwidth(width)
        file.setframerate(rate)
        file.writeframes(samples.tobytes())
    return path
