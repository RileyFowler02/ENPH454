"""Leak-location analysis for two synchronously sampled Red Pitaya channels."""

# dataclass creates a clearly named container for all analysis outputs.
from dataclasses import dataclass

# NumPy provides arrays and the inverse-transform operations.
import numpy as np
# SciPy supplies the frequency-domain and signal-processing calculations.
from scipy.signal import coherence, csd, hilbert


DEFAULT_WAVE_SPEED_M_PER_S = 412.0
DEFAULT_COHERENCE_THRESHOLD = 0.08
MIN_ANALYSIS_FREQUENCY_HZ = 1400.0
MAX_ANALYSIS_FREQUENCY_HZ = 3400.0
TAU_OFFSET_S = -0.00101
WELCH_SEGMENT_LENGTH = 2048
WELCH_OVERLAP = 0.5

# filter low-freq prior to processing (value would need to be determined experimentally (possibly 20hz), )
# look at scipy butterworth filter functino
# flat pass band
# order determines how fast we fit the cutoff freq (i.e., rise speed)

@dataclass(frozen=True)
class LeakAnalysis:
    """Results from coherence-filtered cross-correlation analysis."""

    # Frequencies represented by the cross-spectrum and coherence arrays.
    frequency_hz: np.ndarray
    # Complex relationship between the two recorded channels.
    cross_spectrum: np.ndarray
    # Similarity of the channels at each frequency, from 0 to 1.
    coherence: np.ndarray
    # Boolean mask identifying frequencies that pass the coherence filter.
    leak_band: np.ndarray
    # Time delays represented by the correlation array.
    lag_s: np.ndarray
    # Filtered cross-correlation between the two channels.
    correlation: np.ndarray
    # Magnitude of the analytic correlation signal
    envelope: np.ndarray
    # Delay at the largest envelope peak after applying the fixed tau offset.
    peak_lag_s: float
    # Estimated distance from sensor 1 to the leak.
    leak_distance_m: float
    # Number of samples used in each spectral analysis segment.
    segment_length: int


def apply_powerline_harmonic_filter(
    samples: np.ndarray,
    sampling_rate_hz: float,
    bandwidth_hz: float,
    fundamental_hz: float = 60.0,
) -> np.ndarray:
    """Return a copy with the fundamental and its harmonics removed."""
    if sampling_rate_hz <= 0:
        raise ValueError("Sampling rate must be greater than zero.")
    if not np.isfinite(bandwidth_hz) or bandwidth_hz < 0:
        raise ValueError("Harmonic filter bandwidth must be finite and non-negative.")
    if fundamental_hz <= 0:
        raise ValueError("Fundamental frequency must be greater than zero.")

    values = np.asarray(samples, dtype=float)
    if values.ndim != 1:
        raise ValueError("Samples must be one-dimensional.")
    if len(values) < 2 or bandwidth_hz == 0:
        return values.copy()

    frequencies = np.fft.rfftfreq(len(values), d=1 / sampling_rate_hz)
    keep = np.ones(frequencies.shape, dtype=bool)
    half_bandwidth = bandwidth_hz / 2
    harmonic = fundamental_hz
    nyquist_hz = sampling_rate_hz / 2
    while harmonic <= nyquist_hz:
        keep &= np.abs(frequencies - harmonic) > half_bandwidth
        harmonic += fundamental_hz

    return np.fft.irfft(np.fft.rfft(values) * keep, n=len(values))


def analyze_leak(
    channel_1: np.ndarray,
    channel_2: np.ndarray,
    sampling_rate_hz: float,
    wave_speed_m_per_s: float = DEFAULT_WAVE_SPEED_M_PER_S,
    sensor_spacing_m: float = 4.0,
    coherence_threshold: float = DEFAULT_COHERENCE_THRESHOLD,
    harmonic_bandwidth_hz: float = 0.0,
    frequency_threshold_hz: float = MIN_ANALYSIS_FREQUENCY_HZ,
) -> LeakAnalysis:
    """Estimate leak location using coherence-filtered cross-correlation."""
    # Reject physically or mathematically invalid analysis settings first.
    if sampling_rate_hz <= 0:
        raise ValueError("Sampling rate must be greater than zero.")
    if wave_speed_m_per_s <= 0:
        raise ValueError("Wave speed must be greater than zero.")
    if sensor_spacing_m <= 0:
        raise ValueError("Sensor spacing must be greater than zero.")
    if not 0 <= coherence_threshold <= 1:
        raise ValueError("Coherence threshold must be between 0 and 1.")
    if not np.isfinite(harmonic_bandwidth_hz) or harmonic_bandwidth_hz < 0:
        raise ValueError(
            "Harmonic filter bandwidth must be finite and non-negative."
        )
    if not np.isfinite(frequency_threshold_hz) or frequency_threshold_hz < 0:
        raise ValueError(
            "Minimum analysis frequency must be finite and non-negative."
        )

    # Convert inputs to floating-point one-dimensional arrays for SciPy.
    x1 = np.asarray(channel_1, dtype=float)
    x2 = np.asarray(channel_2, dtype=float)
    # Both signals must be simple, matching-length sample sequences.
    if x1.ndim != 1 or x2.ndim != 1:
        raise ValueError("Both channels must be one-dimensional.")
    if len(x1) != len(x2):
        raise ValueError("Both channels must contain the same number of samples.")
    if len(x1) < 2:
        raise ValueError("At least two samples are required.")

    # Filter only the in-memory analysis arrays; the loaded recording remains
    # unchanged and can still be displayed as the original signal.
    x1 = apply_powerline_harmonic_filter(
        x1, sampling_rate_hz, harmonic_bandwidth_hz
    )
    x2 = apply_powerline_harmonic_filter(
        x2, sampling_rate_hz, harmonic_bandwidth_hz
    )

    # Short recordings use their full length because SciPy requires nperseg
    # not to exceed the number of available samples.
    segment_length = min(WELCH_SEGMENT_LENGTH, len(x1))
    noverlap = int(segment_length * WELCH_OVERLAP)

    # Estimate the cross-spectrum, which describes how the channels relate at
    # each frequency.
    frequency_hz, cross_spectrum = csd(
        x1, x2, fs=sampling_rate_hz, nperseg=segment_length, noverlap=noverlap
    )
    # Estimate magnitude-squared coherence to identify shared signal content.
    _, coherence_values = coherence(
        x1, x2, fs=sampling_rate_hz, nperseg=segment_length, noverlap=noverlap
    )
    analysis_band = (
        (frequency_hz >= max(frequency_threshold_hz, MIN_ANALYSIS_FREQUENCY_HZ))
        & (frequency_hz <= MAX_ANALYSIS_FREQUENCY_HZ)
    )
    coherence_values[~analysis_band] = 0

    # Keep only frequencies whose coherence exceeds the user-selected cutoff.
    leak_band = coherence_values > coherence_threshold
    # Preserve the phase of selected cross-spectrum values while normalizing
    # their magnitude; rejected frequencies become zero.
    filtered_cross_spectrum = (
        cross_spectrum
        * leak_band
        / (np.abs(cross_spectrum) + np.finfo(float).eps)
    )
    # Transform the filtered spectrum back to a centered time-domain
    # correlation signal.
    correlation = np.fft.fftshift(np.fft.irfft(filtered_cross_spectrum))
    # The envelope captures the size of oscillations regardless of sign.
    envelope = np.abs(hilbert(correlation))

    # Map correlation-array positions to delays in seconds.
    lag_samples = np.arange(len(correlation)) - len(correlation) // 2
    lag_s = lag_samples / sampling_rate_hz
    # The maximum envelope value is the selected propagation delay.
    peak_index = int(np.argmax(envelope))
    peak_lag_s = float(lag_s[peak_index]) + TAU_OFFSET_S
    # With sensors on a pipe, this equation converts delay to distance from
    # the first sensor using the known spacing and wave speed.
    leak_distance_m = (sensor_spacing_m - wave_speed_m_per_s * peak_lag_s) / 2

    # Package every intermediate result needed by the dashboard.
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
