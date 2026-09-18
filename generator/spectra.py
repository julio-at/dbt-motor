"""
Spectrum generation: waveform snapshots → FFT (SPEC §3.3, §5.3).

Periodic waveform captures (every 60 min default). Synthesize from signal components,
apply Hann window, FFT, output velocity RMS per bin.
"""

import numpy as np
from datetime import datetime
from typing import List, Tuple
from generator.signal import MotorSignal


def synthesize_waveform(
    signal: MotorSignal,
    axis: str,
    fs_hz: float,
    duration_sec: float,
    rng: np.random.Generator,
) -> np.ndarray:
    """
    Synthesize a waveform from signal components.

    Args:
        signal: MotorSignal (contains X/Y/Z axis components)
        axis: 'X', 'Y', or 'Z'
        fs_hz: sampling frequency (Hz, default 2560)
        duration_sec: capture duration (seconds, default 1)
        rng: random number generator

    Returns:
        waveform array (time-domain displacement, µm)

    SPEC §5.3: waveform is sum of components (f_i, v_rms_i) + broadband noise,
    windowed (Hann) and FFT-ed with numpy.
    """
    n_samples = int(fs_hz * duration_sec)
    t = np.arange(n_samples) / fs_hz
    waveform = np.zeros(n_samples)

    # Select axis components
    if axis == "X":
        components = signal.x_axis.components
    elif axis == "Y":
        components = signal.y_axis.components
    elif axis == "Z":
        components = signal.z_axis.components
    else:
        return waveform

    # Sum components: convert v_rms to displacement and synthesize sine
    for comp in components:
        # v_rms_mm_s to d_pp_um
        d_pp = comp.amplitude_um_pp()
        d_peak = d_pp / 2

        # Sinusoid: d(t) = d_peak * sin(2π * f * t)
        waveform += d_peak * np.sin(2 * np.pi * comp.frequency_hz * t)

    # Add broadband noise floor (~5% of max displacement)
    noise_level = np.max(np.abs(waveform)) * 0.05 if np.max(np.abs(waveform)) > 0 else 0.1
    waveform += rng.normal(0, noise_level / 3, n_samples)

    return waveform


def waveform_to_spectrum(
    waveform: np.ndarray,
    fs_hz: float,
    f_max_hz: float = 1000.0,
) -> Tuple[List[float], float]:
    """
    Convert waveform (displacement, µm) to velocity RMS spectrum.

    Args:
        waveform: displacement waveform (µm)
        fs_hz: sampling frequency (Hz)
        f_max_hz: max frequency to keep (Hz, default 1000)

    Returns:
        (bins_velocity_rms, df_hz) where bins is velocity RMS per frequency bin

    SPEC §3.3: velocity RMS per bin, Hann window, 1 Hz resolution (for default 2560 Hz, 2560 samples).

    Physics: displacement → velocity via differentiation in frequency domain.
    v_rms = sqrt(2) * π * f * d_rms / √2 = π * f * d_rms
    """
    n_samples = len(waveform)

    # Apply Hann window (SPEC §3.3: window="hann")
    window = np.hanning(n_samples)
    waveform_windowed = waveform * window

    # FFT: displacement domain
    fft_disp = np.fft.fft(waveform_windowed)
    freqs = np.fft.fftfreq(n_samples, 1 / fs_hz)

    # Convert to one-sided spectrum (DC to fs/2)
    idx_positive = freqs >= 0
    freqs_positive = freqs[idx_positive]
    fft_positive = fft_disp[idx_positive]

    # Displacement RMS per bin
    d_rms_bins = np.abs(fft_positive) / (n_samples / 2)
    d_rms_bins[0] /= 2  # DC component

    # Convert to velocity RMS: v_rms = π * f * d_rms
    v_rms_bins = np.pi * freqs_positive * d_rms_bins

    # Truncate to f_max_hz and convert to list
    idx_max = np.searchsorted(freqs_positive, f_max_hz)
    v_rms_trunc = v_rms_bins[:idx_max].tolist()

    # Frequency resolution
    df_hz = fs_hz / n_samples

    return v_rms_trunc, df_hz


def generate_spectrum(
    device_id: str,
    axis: str,
    signal: MotorSignal,
    ts: datetime,
    fs_hz: float = 2560,
    n_samples: int = 2560,
    rng: np.random.Generator = None,
) -> dict:
    """
    Generate a spectrum snapshot (one per device × axis).

    Args:
        device_id: sensor ID (e.g., 'VS-000123')
        axis: 'X', 'Y', or 'Z'
        signal: MotorSignal with components
        ts: snapshot timestamp
        fs_hz: sampling frequency (Hz, default 2560)
        n_samples: number of samples (default 2560, 1 sec @ 2560 Hz)
        rng: random number generator

    Returns:
        dict with spectrum metadata and bins (velocity RMS per frequency bin)
    """
    if rng is None:
        rng = np.random.default_rng()

    duration_sec = n_samples / fs_hz
    waveform = synthesize_waveform(signal, axis, fs_hz, duration_sec, rng)
    bins, df_hz = waveform_to_spectrum(waveform, fs_hz)

    f_max_hz = df_hz * len(bins)

    return {
        "timestamp": ts,
        "device_ID": device_id,
        "axis": axis,
        "fs_hz": fs_hz,
        "n_samples": n_samples,
        "window": "hann",
        "df_hz": df_hz,
        "f_max_hz": f_max_hz,
        "unit": "mm/s_rms",
        "bins": bins,
    }
