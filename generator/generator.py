"""
Main generator: orchestrate frame/drive/truth generation.

Simulates a plant over time with scenarios, varying operating conditions, and data quality issues.
"""

import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Tuple
from generator.assets import Asset, create_plant_a
from generator.physics import running_speed, bearing_defect_frequencies
from generator.signal import (
    baseline_signal, fault_unbalance_growth, fault_bearing_outer_race,
    fault_misalignment, fault_lubrication_loss,
)
from generator.output import FramesWriter, DriveTelemWriter, SpectraWriter, TruthLabelsWriter
from generator.spectra import generate_spectrum


class PlantSimulator:
    """Simulate motor plant over time."""

    def __init__(self, assets: List[Asset], profile: str, seed: int = 42):
        self.assets = assets
        self.profile = profile
        self.rng = np.random.default_rng(seed)
        self.asset_signals = {a.device_id: baseline_signal(a.specs.rated_hz, a.specs, self.rng)
                              for a in assets}
        self.asset_temps = {a.device_id: 25.0 for a in assets}
        self.asset_humidities = {a.device_id: 60.0 for a in assets}

        # Fault injection: asset_id -> (scenario, start_ts, end_ts, failure_ts)
        self.faults = {}

        # Ambient conditions
        self.ambient_temp = 25.0
        self.ambient_humidity = 60.0

    def set_fault(self, asset_id: str, scenario: str, start_ts: datetime, end_ts: datetime,
                  failure_ts: datetime):
        """Inject a fault scenario."""
        self.faults[asset_id] = (scenario, start_ts, end_ts, failure_ts)

    def update_conditions(self, ts: datetime, duration_days: int):
        """Update ambient temperature/humidity over the simulation."""
        # Daily cycle: 24-32°C, RH 60-95% inversely correlated
        day_of_sim = (ts - datetime(2026, 1, 1)).days % duration_days
        frac = day_of_sim / duration_days

        # Simple sine wave for ambient conditions
        hour_of_day = ts.hour + ts.minute / 60
        cycle = np.sin(2 * np.pi * hour_of_day / 24)
        self.ambient_temp = 24 + 8 * np.sin(2 * np.pi * frac)  # 24-32°C
        self.ambient_humidity = 95 - 35 * np.sin(2 * np.pi * frac)  # 60-95%, inverse

    def simulate_frame(self, asset: Asset, ts: datetime, output_hz: float,
                       duration_days: int) -> dict:
        """Generate a vibration frame."""
        self.update_conditions(ts, duration_days)

        device_id = asset.device_id
        sig = self.asset_signals[device_id]

        # Apply fault if active
        if asset.asset_id in self.faults:
            scenario, start_ts, end_ts, failure_ts = self.faults[asset.asset_id]
            if start_ts <= ts <= end_ts:
                progress = (ts - start_ts).total_seconds() / (end_ts - start_ts).total_seconds()

                if scenario == "UNBALANCE_GROWTH":
                    sig = fault_unbalance_growth(sig, progress, self.rng)
                elif scenario == "BEARING_OUTER_RACE":
                    f_sync, f_1x, _ = running_speed(output_hz, asset.specs)
                    bpfo = bearing_defect_frequencies(f_1x, n=8)["BPFO"]
                    sig = fault_bearing_outer_race(sig, bpfo, progress, self.rng)
                elif scenario == "MISALIGNMENT_AFTER_MAINT":
                    f_sync, f_1x, _ = running_speed(output_hz, asset.specs)
                    sig = fault_misalignment(sig, f_1x, progress, self.rng)
                elif scenario == "LUBRICATION_LOSS":
                    sig, temp_rise = fault_lubrication_loss(sig, progress, self.rng)
                    self.asset_temps[device_id] = self.ambient_temp + 20 + temp_rise

        x_amp = sig.x_axis.total_amplitude_um_pp(self.rng)
        y_amp = sig.y_axis.total_amplitude_um_pp(self.rng)
        z_amp = sig.z_axis.total_amplitude_um_pp(self.rng)

        x_freq = sig.x_axis.dominant_frequency()
        y_freq = sig.y_axis.dominant_frequency()
        z_freq = sig.z_axis.dominant_frequency()

        # Temperature influenced by load and fault
        temp_load_rise = 5 if output_hz > 0.7 * asset.specs.rated_hz else 0
        self.asset_temps[device_id] = self.ambient_temp + 15 + temp_load_rise
        self.asset_humidities[device_id] = self.ambient_humidity

        # Add jitter to frequencies (±0.5%, SPEC §5.3)
        x_freq *= (1 + self.rng.normal(0, 0.005))
        y_freq *= (1 + self.rng.normal(0, 0.005))
        z_freq *= (1 + self.rng.normal(0, 0.005))

        return {
            "timestamp": ts,
            "device_ID": device_id,
            "X_amplitude": x_amp,
            "X_frequency": max(0, x_freq),
            "Y_amplitude": y_amp,
            "Y_frequency": max(0, y_freq),
            "Z_amplitude": z_amp,
            "Z_frequency": max(0, z_freq),
            "temperature": self.asset_temps[device_id],
            "relative_humidity": self.asset_humidities[device_id],
            "coordinates_position": f"[{asset.floor},{asset.tandem},{asset.order_pos}]",
        }

    def simulate_drive_telemetry(self, asset: Asset, ts: datetime) -> dict:
        """Generate drive telemetry."""
        # Simulate VFD setpoint changes every 30-120 minutes
        seconds_since_start = (ts - datetime(2026, 1, 1)).total_seconds()
        period_sec = self.rng.integers(30 * 60, 120 * 60)
        cycle_pos = (seconds_since_start % period_sec) / period_sec

        # Output Hz: 35-60 Hz (nominal 60 for conveyor)
        output_hz = 35 + 25 * np.sin(2 * np.pi * cycle_pos)
        if output_hz < 5:
            output_hz = 0  # stopped

        # Voltages (line-to-line RMS)
        v_avg = 480 + self.rng.normal(0, 5)
        v_l1l2 = v_avg + self.rng.normal(0, 3)
        v_l2l3 = v_avg + self.rng.normal(0, 3)
        v_l3l1 = v_avg + self.rng.normal(0, 3)

        # Currents (proportional to load)
        i_nominal = asset.specs.rated_current_a
        load_pct = 50 + 30 * np.sin(2 * np.pi * cycle_pos)
        i_avg = (i_nominal * load_pct / 100) + self.rng.normal(0, 1)
        i_l1 = i_avg + self.rng.normal(0, 0.5)
        i_l2 = i_avg + self.rng.normal(0, 0.5)
        i_l3 = i_avg + self.rng.normal(0, 0.5)

        # Phase angles
        angle_l1 = self.rng.uniform(0, 60)
        angle_l2 = angle_l1 + 120 + self.rng.normal(0, 5)
        angle_l3 = angle_l1 + 240 + self.rng.normal(0, 5)

        # Power factor
        pf = 0.85 + self.rng.normal(0, 0.05)
        pf = max(0.7, min(1.0, pf))

        # Run state
        run_state = "RUN" if output_hz > 5 else "STOP"

        return {
            "timestamp": ts,
            "drive_id": asset.drive_id,
            "output_hz": max(0, output_hz),
            "voltage_l1l2_v": v_l1l2,
            "voltage_l2l3_v": v_l2l3,
            "voltage_l3l1_v": v_l3l1,
            "current_l1_a": i_l1,
            "current_l2_a": i_l2,
            "current_l3_a": i_l3,
            "phase_angle_l1_deg": angle_l1,
            "phase_angle_l2_deg": angle_l2,
            "phase_angle_l3_deg": angle_l3,
            "power_factor": pf,
            "run_state": run_state,
        }

    def simulate_spectra(self, asset: Asset, ts: datetime, output_hz: float,
                        duration_days: int) -> list:
        """
        Generate spectra for all axes (X, Y, Z).

        SPEC §3.3: 1 snapshot per device × axis per spectrum interval (default 60 min).
        """
        self.update_conditions(ts, duration_days)
        device_id = asset.device_id
        sig = self.asset_signals[device_id]

        # Apply fault if active (same as frame generation)
        if asset.asset_id in self.faults:
            scenario, start_ts, end_ts, failure_ts = self.faults[asset.asset_id]
            if start_ts <= ts <= end_ts:
                progress = (ts - start_ts).total_seconds() / (end_ts - start_ts).total_seconds()

                if scenario == "UNBALANCE_GROWTH":
                    sig = fault_unbalance_growth(sig, progress, self.rng)
                elif scenario == "BEARING_OUTER_RACE":
                    f_sync, f_1x, _ = running_speed(output_hz, asset.specs)
                    bpfo = bearing_defect_frequencies(f_1x, n=8)["BPFO"]
                    sig = fault_bearing_outer_race(sig, bpfo, progress, self.rng)
                elif scenario == "MISALIGNMENT_AFTER_MAINT":
                    f_sync, f_1x, _ = running_speed(output_hz, asset.specs)
                    sig = fault_misalignment(sig, f_1x, progress, self.rng)

        spectra = []
        for axis in ["X", "Y", "Z"]:
            spectrum = generate_spectrum(device_id, axis, sig, ts, rng=self.rng)
            spectra.append(spectrum)

        return spectra
