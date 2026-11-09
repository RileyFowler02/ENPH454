"""Leak-location analysis for two synchronously sampled Red Pitaya channels."""

from dataclasses import dataclass

import numpy as np
from scipy.signal import coherence, csd, hilbert, welch


@dataclass(frozen=True)
class LeakAnalysis:
    """Results from coherence-filtered cross-correlation analysis."""

    frequency_hz: np.ndarray
    cross_spectrum: np.ndarray
    coherence: np.ndarray
    leak_band: np.ndarray
    lag_s: np.ndarray
    correlation: np.ndarray
    envelope: np.ndarray
    peak_lag_s: float
    leak_distance_m: float
    segment_length: int


def analyze_leak(
    channel_1: np.ndarray,
    channel_2: np.ndarray,
    sampling_rate_hz: float,
    wave_speed_m_per_s: float = 1400.0,
    sensor_spacing_m: float = 4.0,
    segments: int = 16,
    overlap: float = 0.75,
    coherence_threshold: float = 0.4,
) -> LeakAnalysis:
    """Estimate leak location using coherence-filtered cross-correlation."""
    if sampling_rate_hz <= 0:
        raise ValueError("Sampling rate must be greater than zero.")
    if wave_speed_m_per_s <= 0:
        raise ValueError("Wave speed must be greater than zero.")
    if sensor_spacing_m <= 0:
        raise ValueError("Sensor spacing must be greater than zero.")
    if segments < 1:
        raise ValueError("Number of segments must be at least one.")
    if not 0 <= overlap < 1:
        raise ValueError("Overlap must be at least 0 and less than 1.")
    if not 0 <= coherence_threshold <= 1:
        raise ValueError("Coherence threshold must be between 0 and 1.")

    x1 = np.asarray(channel_1, dtype=float)
    x2 = np.asarray(channel_2, dtype=float)
    if x1.ndim != 1 or x2.ndim != 1:
        raise ValueError("Both channels must be one-dimensional.")
    if len(x1) != len(x2):
        raise ValueError("Both channels must contain the same number of samples.")
    if len(x1) < 2:
        raise ValueError("At least two samples are required.")

    segment_length = max(
        2,
        int(len(x1) / (1 + (segments - 1) * (1 - overlap))),
    )
    segment_length = min(segment_length, len(x1))
    noverlap = min(int(segment_length * overlap), segment_length - 1)

    frequency_hz, cross_spectrum = csd(
        x1, x2, fs=sampling_rate_hz, nperseg=segment_length, noverlap=noverlap
    )
    _, coherence_values = coherence(
        x1, x2, fs=sampling_rate_hz, nperseg=segment_length, noverlap=noverlap
    )

    leak_band = coherence_values > coherence_threshold
    filtered_cross_spectrum = (
        cross_spectrum
        * leak_band
        / (np.abs(cross_spectrum) + np.finfo(float).eps)
    )
    correlation = np.fft.fftshift(np.fft.irfft(filtered_cross_spectrum))
    envelope = np.abs(hilbert(correlation))

    lag_samples = np.arange(len(correlation)) - len(correlation) // 2
    lag_s = lag_samples / sampling_rate_hz
    peak_index = int(np.argmax(envelope))
    peak_lag_s = float(lag_s[peak_index])
    leak_distance_m = (sensor_spacing_m - wave_speed_m_per_s * peak_lag_s) / 2

    return LeakAnalysis(
        frequency_hz=frequency_hz,
        cross_spectrum=cross_spectrum,
        coherence=coherence_values,
        leak_band=leak_band,
        lag_s=lag_s,
        correlation=correlation,
        envelope=envelope,
        peak_lag_s=peak_lag_s,
        leak_distance_m=float(leak_distance_m),
        segment_length=segment_length,
    )
