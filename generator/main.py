#!/usr/bin/env python3
"""
Synthetic motor vibration data generator (SPEC §5).

Generates:
- vibration_frames_*.csv.gz (overall amplitudes, dominant frequencies)
- drive_telemetry_*.csv.gz (VFD speed, voltage, current, power factor)
- spectra_*.ndjson.gz (waveform snapshots → FFT spectra)
- truth/labels.csv (ground truth: failure scenarios, start/end times)

Profiles: dev (21d, 12 assets), demo (30d, 24 assets), full (3d, 24 assets, 2fps)
Deterministic: same seed → same data.
"""

import argparse
import sys
from pathlib import Path
from datetime import datetime, timedelta
import numpy as np
from generator.assets import create_plant_a
from generator.generator import PlantSimulator
from generator.output import FramesWriter, DriveTelemWriter, SpectraWriter, TruthLabelsWriter


PROFILE_CONFIG = {
    "dev": {"duration_days": 21, "frame_interval_sec": 10, "spectrum_interval_min": 60},
    "demo": {"duration_days": 30, "frame_interval_sec": 2, "spectrum_interval_min": 60},
    "full": {"duration_days": 3, "frame_interval_sec": 0.5, "spectrum_interval_min": 10},
}


def generate(profile: str, seed: int, output_dir: Path):
    """Generate synthetic data."""
    output_dir = output_dir / profile
    output_dir.mkdir(parents=True, exist_ok=True)

    config = PROFILE_CONFIG[profile]
    duration_days = config["duration_days"]
    frame_interval_sec = config["frame_interval_sec"]
    spectrum_interval_min = config.get("spectrum_interval_min", 60)

    print(f"[gen] Profile: {profile}")
    print(f"[gen]   Duration: {duration_days} days")
    print(f"[gen]   Frame interval: {frame_interval_sec} sec")
    print(f"[gen]   Spectrum interval: {spectrum_interval_min} min")
    print(f"[gen]   Seed: {seed}")

    # Create assets and simulator
    assets = create_plant_a(profile)
    n_assets = len(assets)
    print(f"[gen]   Assets: {n_assets}")

    sim = PlantSimulator(assets, profile, seed=seed)

    # Inject fault scenarios (per asset, v1 keeps it simple)
    if n_assets >= 1:
        start_ts = datetime(2026, 1, 8)
        end_ts = datetime(2026, 1, 15)
        failure_ts = datetime(2026, 1, 14)
        sim.set_fault(assets[0].asset_id, "UNBALANCE_GROWTH", start_ts, end_ts, failure_ts)

    if n_assets >= 2:
        start_ts = datetime(2026, 1, 10)
        end_ts = datetime(2026, 1, 20)
        failure_ts = datetime(2026, 1, 19)
        sim.set_fault(assets[1].asset_id, "BEARING_OUTER_RACE", start_ts, end_ts, failure_ts)

    # Output writers
    frames_out = FramesWriter(output_dir)
    drive_out = DriveTelemWriter(output_dir)
    spectra_out = SpectraWriter(output_dir)
    truth_out = TruthLabelsWriter(output_dir)

    print("[gen] Generating frames, drive telemetry, and spectra...")
    start_dt = datetime(2026, 1, 1, 0, 0, 0)
    end_dt = start_dt + timedelta(days=duration_days)
    current_dt = start_dt
    label_id = 1

    frame_count = 0
    drive_count = 0
    spectrum_count = 0
    last_spectrum_dt = start_dt - timedelta(minutes=spectrum_interval_min + 1)

    # Generate frames, drive telemetry, and spectra
    while current_dt < end_dt:
        for asset in assets:
            output_hz = 50 + 10 * np.sin(2 * np.pi * current_dt.hour / 24)
            frame = sim.simulate_frame(asset, current_dt, output_hz, duration_days)
            frames_out.write(frame)
            frame_count += 1

        # Drive telemetry every 10 seconds (1/10th of frames)
        if frame_count % 10 == 0:
            for asset in assets:
                drive = sim.simulate_drive_telemetry(asset, current_dt)
                drive_out.write(drive)
                drive_count += 1

        # Spectra at interval (e.g., every 60 min, only while running)
        if (current_dt - last_spectrum_dt).total_seconds() >= spectrum_interval_min * 60:
            for asset in assets:
                output_hz = 50 + 10 * np.sin(2 * np.pi * current_dt.hour / 24)
                if output_hz > 5:  # Only capture when running
                    spectra = sim.simulate_spectra(asset, current_dt, output_hz, duration_days)
                    for spectrum in spectra:
                        spectra_out.write(spectrum)
                        spectrum_count += 1
            last_spectrum_dt = current_dt

        current_dt += timedelta(seconds=frame_interval_sec)

    frames_out.close()
    drive_out.close()
    spectra_out.close()

    print(f"[gen] ✓ Frames: {frame_count}")
    print(f"[gen] ✓ Drive telemetry: {drive_count}")
    print(f"[gen] ✓ Spectra: {spectrum_count}")

    # Write truth labels
    for asset_id, (scenario, start_ts, end_ts, failure_ts) in sim.faults.items():
        asset = next((a for a in assets if a.asset_id == asset_id), None)
        if asset:
            truth_out.write({
                "label_id": label_id,
                "asset_id": asset_id,
                "device_ID": asset.device_id,
                "scenario": scenario,
                "start_ts": start_ts,
                "functional_failure_ts": failure_ts,
                "end_ts": end_ts,
                "expected_reasons": f"{scenario}",
            })
            label_id += 1

    truth_out.close()
    print(f"[gen] ✓ Truth labels: {label_id - 1}")

    print(f"[gen] Output: {output_dir}")
    print("[gen] Done.")


def main():
    parser = argparse.ArgumentParser(description="Generate synthetic motor data")
    parser.add_argument("--profile", choices=["dev", "demo", "full"], default="dev")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output-dir", type=Path, default=Path("data"))
    args = parser.parse_args()

    try:
        generate(args.profile, args.seed, args.output_dir)
        return 0
    except Exception as e:
        print(f"[gen] ✗ Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
