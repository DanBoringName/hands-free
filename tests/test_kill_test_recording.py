"""Gaps and the band edge, read from a recording."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from support import RATE, muffled, noise, write_wav

from hands_free.kill_test.recording import (
    Gap,
    Recording,
    RecordingError,
    band_edge,
    loud_spectrum,
    read_wav,
    silent_gaps,
)


def recording(samples: np.ndarray, rate: int = RATE) -> Recording:
    return Recording(samples.astype(np.int16), rate)


def test_a_mono_16_bit_wav_reads_back(tmp_path: Path):
    samples = noise(1.0)
    read = read_wav(write_wav(tmp_path / "phone.wav", samples))
    assert read.rate == RATE
    assert np.array_equal(read.samples, samples)
    assert read.seconds == pytest.approx(1.0)


@pytest.mark.parametrize(("channels", "width"), [(2, 2), (1, 1), (1, 4)])
def test_anything_but_one_channel_of_16_bits_is_refused(
    tmp_path: Path, channels: int, width: int
):
    path = write_wav(tmp_path / "mix.wav", noise(1.0), channels=channels, width=width)
    with pytest.raises(RecordingError, match="one channel of 16-bit PCM"):
        read_wav(path)


@pytest.mark.parametrize("content", [b"", b"OggS not a wav at all"])
def test_a_file_that_is_not_a_wav_is_refused(tmp_path: Path, content: bytes):
    path = tmp_path / "phone.ogg"
    path.write_bytes(content)
    with pytest.raises(RecordingError, match="not a PCM WAV file"):
        read_wav(path)


def test_a_hole_in_the_audio_is_found_where_it_is():
    samples = noise(10.0)
    samples[round(3.0 * RATE) : round(5.5 * RATE)] = 0
    [gap] = silent_gaps(recording(samples), shortest=0.5)
    assert gap.start == pytest.approx(3.0, abs=0.01)
    assert gap.length == pytest.approx(2.5, abs=0.02)


def test_a_hole_shorter_than_the_shortest_is_left_out():
    samples = noise(5.0)
    samples[RATE : RATE + round(0.3 * RATE)] = 0
    assert silent_gaps(recording(samples), shortest=0.5) == []


def test_a_hole_at_the_end_is_a_gap():
    samples = noise(4.0)
    samples[3 * RATE :] = 0
    assert silent_gaps(recording(samples), shortest=0.5) == [Gap(3.0, 1.0)]


@pytest.mark.parametrize("seconds", [0.0, 0.004])
def test_too_short_for_a_frame_has_no_gaps(seconds: float):
    assert silent_gaps(recording(np.zeros(round(seconds * RATE))), shortest=0.5) == []


def test_quiet_audio_is_not_a_gap():
    """A room tone of one bit either way is still something arriving."""
    samples = np.random.default_rng(3).integers(-1, 2, 5 * RATE)
    samples[samples == 0] = 1
    assert silent_gaps(recording(samples), shortest=0.5) == []


@pytest.mark.parametrize("cutoff", [3900.0, 7900.0, 12000.0])
def test_a_cut_is_found_where_the_band_stops(cutoff: float):
    spectrum = loud_spectrum(recording(noise(20.0, cutoff)))
    assert spectrum is not None
    edge = band_edge(spectrum)
    assert edge is not None
    assert edge.frequency == pytest.approx(cutoff, abs=200)
    assert edge.fall_db > 40


def test_full_band_audio_has_no_cut():
    spectrum = loud_spectrum(recording(noise(20.0)))
    assert spectrum is not None
    assert band_edge(spectrum) is None


def test_a_muffled_mic_fades_rather_than_cuts():
    spectrum = loud_spectrum(recording(muffled(20.0)))
    assert spectrum is not None
    assert band_edge(spectrum) is None


def test_the_spectrum_is_taken_from_the_loudest_quarter():
    samples = noise(20.0) // 50
    samples[: 5 * RATE] = noise(5.0, cutoff=7900.0)
    spectrum = loud_spectrum(recording(samples))
    assert spectrum is not None
    assert spectrum.seconds == pytest.approx(5.0, abs=0.1)
    edge = band_edge(spectrum)
    assert edge is not None
    assert edge.frequency == pytest.approx(7900.0, abs=200)


@pytest.mark.parametrize("samples", [np.zeros(5 * RATE), np.zeros(100)])
def test_silence_has_no_spectrum(samples: np.ndarray):
    assert loud_spectrum(recording(samples)) is None


def test_a_recording_too_narrow_to_search_has_no_cut():
    spectrum = loud_spectrum(recording(noise(5.0)[::8], rate=6000))
    assert spectrum is not None
    assert band_edge(spectrum) is None
