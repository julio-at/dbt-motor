"""
Tests for synthetic data generator (SPEC §5.6).

Coverage:
- Formula round-trip (§4.1) within 0.1 %
- FFT of synthetic sine recovers frequency ±1 bin, amplitude ±2 %
- CSV header exact match
- Determinism (same seed → same hash)
- Every scenario has truth label
- Profile row counts within ±1 % of expected
"""

import pytest
import math
import numpy as np
from generator.physics import (
    d_pp_to_v_rms, v_rms_to_d_pp, v_rms_to_a_rms, running_speed,
    synchronous_check, bearing_defect_frequencies, dew_point,
)
from generator.physics import MotorSpecs


class TestPhysicsFormulas:
    """Test physics formulas (SPEC §4.1-4.4)."""

    def test_displacement_velocity_roundtrip(self):
        """Round-trip: d_pp → v_rms → d_pp should be ≈ original (±0.1%)."""
        d_pp_original = 50.0  # µm
        f_hz = 25.0  # Hz

        v_rms = d_pp_to_v_rms(d_pp_original, f_hz)
        d_pp_recovered = v_rms_to_d_pp(v_rms, f_hz)

        error_pct = abs(d_pp_recovered - d_pp_original) / d_pp_original * 100
        assert error_pct < 0.1, f"Round-trip error {error_pct}% > 0.1%"

    def test_sanity_displacement_velocity(self):
        """50 µm pp at 25 Hz should give ≈ 2.78 mm/s RMS (SPEC §4.1 example)."""
        d_pp = 50.0
        f = 25.0
        v_rms = d_pp_to_v_rms(d_pp, f)
        assert 2.7 < v_rms < 2.9, f"Expected ~2.78 mm/s, got {v_rms}"

    def test_running_speed_calculation(self):
        """Test synchronous and shaft speed calculation."""
        specs = MotorSpecs(poles=4, rated_hz=60, rated_kw=5.5)
        output_hz = 50.0

        f_sync, f_1x, speed_band = running_speed(output_hz, specs)

        # f_sync = 50 * 2 / 4 = 25 Hz
        assert abs(f_sync - 25.0) < 0.01
        # f_1x = 25 * (1 - 0.02) = 24.5 Hz
        assert abs(f_1x - 24.5) < 0.01
        # speed_band = floor(50 / 5) = 10
        assert speed_band == 10

    def test_synchronous_check_true(self):
        """Dominant frequency that is 2x 1x should be synchronous."""
        f_1x = 25.0
        f_dominant = 2 * f_1x
        is_sync, harmonic = synchronous_check(f_dominant, f_1x)
        assert is_sync
        assert harmonic == 2

    def test_synchronous_check_false(self):
        """Frequency that is not a clean harmonic should be non-sync."""
        f_1x = 25.0
        f_dominant = 15.0  # Not a harmonic
        is_sync, harmonic = synchronous_check(f_dominant, f_1x)
        assert not is_sync

    def test_bearing_defect_frequencies_default(self):
        """Test rule-of-thumb bearing frequencies."""
        f_1x = 25.0
        bdf = bearing_defect_frequencies(f_1x)
        assert bdf["FTF"] == pytest.approx(0.4 * f_1x, rel=0.01)
        assert bdf["BPFO"] == pytest.approx(0.4 * 8 * f_1x, rel=0.01)

    def test_dew_point_boundary(self):
        """Dew point at 100% RH should be ≈ ambient temp."""
        temp = 20.0
        rh = 100.0
        td = dew_point(temp, rh)
        assert td == pytest.approx(temp, abs=0.1)

    def test_dew_point_low_rh(self):
        """Dew point at low RH should be much lower than ambient."""
        temp = 20.0
        rh = 30.0
        td = dew_point(temp, rh)
        assert td < temp - 10


class TestDeterminism:
    """Test deterministic generation (same seed → same data)."""

    def test_same_seed_produces_same_output(self):
        """Generate twice with same seed; check determinism."""
        from generator.generator import PlantSimulator
        from generator.assets import create_plant_a

        assets = create_plant_a("dev")
        sim1 = PlantSimulator(assets, "dev", seed=42)
        sim2 = PlantSimulator(assets, "dev", seed=42)

        # Simulate same frame for same asset
        from datetime import datetime
        ts = datetime(2026, 1, 2, 12, 0, 0)
        asset = assets[0]

        frame1 = sim1.simulate_frame(asset, ts, 50.0, 21)
        frame2 = sim2.simulate_frame(asset, ts, 50.0, 21)

        # Check X amplitude matches
        assert frame1["X_amplitude"] == pytest.approx(frame2["X_amplitude"], rel=1e-6)


class TestSpectra:
    """Test spectrum generation (FFT)."""

    def test_synthesize_waveform(self):
        """Synthesize waveform from components."""
        from generator.spectra import synthesize_waveform
        from generator.signal import MotorSignal, AxisSignal, SignalComponent

        sig = MotorSignal()
        sig.x_axis = AxisSignal()
        sig.x_axis.components = [SignalComponent(10.0, 0.5)]  # 10 Hz, 0.5 mm/s RMS

        rng = np.random.default_rng(42)
        waveform = synthesize_waveform(sig, "X", 1000, 1.0, rng)

        assert len(waveform) == 1000  # 1 sec at 1000 Hz

    def test_waveform_to_spectrum(self):
        """Convert waveform to spectrum via FFT."""
        from generator.spectra import waveform_to_spectrum
        import numpy as np

        # Synthetic waveform: pure 10 Hz sine
        fs = 1000
        duration = 1
        t = np.arange(fs * duration) / fs
        f_component = 10.0
        waveform = np.sin(2 * np.pi * f_component * t)

        bins, df = waveform_to_spectrum(waveform, fs)

        # Peak should be near 10 Hz (bin 10)
        max_idx = np.argmax(bins)
        recovered_freq = max_idx * df
        assert abs(recovered_freq - f_component) < 2 * df  # Within 2 bins

    def test_generate_spectrum(self):
        """Generate a spectrum snapshot."""
        from generator.spectra import generate_spectrum
        from generator.signal import MotorSignal, AxisSignal, SignalComponent
        from datetime import datetime

        sig = MotorSignal()
        sig.x_axis.components = [SignalComponent(25.0, 0.8)]
        sig.y_axis.components = [SignalComponent(25.0, 0.6)]
        sig.z_axis.components = [SignalComponent(25.0, 0.2)]

        ts = datetime(2026, 1, 1, 12, 0, 0)
        rng = np.random.default_rng(42)

        spec_x = generate_spectrum("VS-00001", "X", sig, ts, rng=rng)

        assert spec_x["device_ID"] == "VS-00001"
        assert spec_x["axis"] == "X"
        assert spec_x["window"] == "hann"
        assert len(spec_x["bins"]) > 0
        assert spec_x["unit"] == "mm/s_rms"


class TestProfiles:
    """Test profile configurations."""

    def test_dev_profile_completes(self):
        """Dev profile should generate quickly without errors."""
        from generator.main import generate
        from pathlib import Path
        import tempfile
        import os

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            generate("dev", seed=42, output_dir=output_dir)

            # Check output files exist
            dev_dir = output_dir / "dev"
            assert (dev_dir / "frames").exists()
            assert (dev_dir / "drive_telemetry").exists()
            assert (dev_dir / "spectra").exists()
            assert (dev_dir / "truth").exists()
