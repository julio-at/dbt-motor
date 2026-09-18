"""
Output generation: write frames, drive telemetry, spectra to CSV/NDJSON gzip.

Partitioned by arrival hour (SPEC §3.1-3.3).
"""

import gzip
import csv
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Any
from collections import defaultdict


class FramesWriter:
    """Write vibration frames to CSV.gz, partitioned by hour."""

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir / "frames"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.files = {}  # (dt, hh) -> file handle + writer

    def write(self, frame: Dict[str, Any]):
        """Write a frame row. Auto-partitions by timestamp hour."""
        ts = frame["timestamp"]
        dt = ts.strftime("%Y-%m-%d")
        hh = ts.strftime("%H")
        part_dir = self.output_dir / f"dt={dt}" / f"hh={hh}"
        part_dir.mkdir(parents=True, exist_ok=True)

        key = (dt, hh)
        if key not in self.files:
            # New hour partition: create file
            part_file = part_dir / f"part-{len(self.files):03d}.csv.gz"
            f = gzip.open(part_file, "wt", newline="")
            writer = csv.DictWriter(f, fieldnames=[
                "timestamp", "device_ID",
                "X_amplitude", "X_frequency",
                "Y_amplitude", "Y_frequency",
                "Z_amplitude", "Z_frequency",
                "temperature", "relative_humidity",
                "coordinates_position",
            ])
            writer.writeheader()
            self.files[key] = (f, writer)
        else:
            f, writer = self.files[key]

        # Format timestamp ISO-8601 with 9 fractional digits + Z
        ts_str = ts.strftime("%Y-%m-%dT%H:%M:%S") + f".{ts.microsecond:06d}000Z"
        row = dict(frame)
        row["timestamp"] = ts_str
        self.files[key][1].writerow(row)

    def close(self):
        """Close all open files."""
        for f, _ in self.files.values():
            f.close()
        self.files.clear()


class DriveTelemWriter:
    """Write drive telemetry to CSV.gz."""

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir / "drive_telemetry"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.files = {}

    def write(self, telemetry: Dict[str, Any]):
        """Write a telemetry row."""
        ts = telemetry["timestamp"]
        dt = ts.strftime("%Y-%m-%d")
        hh = ts.strftime("%H")
        part_dir = self.output_dir / f"dt={dt}" / f"hh={hh}"
        part_dir.mkdir(parents=True, exist_ok=True)

        key = (dt, hh)
        if key not in self.files:
            part_file = part_dir / f"part-{len(self.files):03d}.csv.gz"
            f = gzip.open(part_file, "wt", newline="")
            writer = csv.DictWriter(f, fieldnames=[
                "timestamp", "drive_id",
                "output_hz",
                "voltage_l1l2_v", "voltage_l2l3_v", "voltage_l3l1_v",
                "current_l1_a", "current_l2_a", "current_l3_a",
                "phase_angle_l1_deg", "phase_angle_l2_deg", "phase_angle_l3_deg",
                "power_factor", "run_state",
            ])
            writer.writeheader()
            self.files[key] = (f, writer)

        ts_str = telemetry["timestamp"].strftime("%Y-%m-%dT%H:%M:%S") + \
                 f".{telemetry['timestamp'].microsecond:06d}000Z"
        row = dict(telemetry)
        row["timestamp"] = ts_str
        self.files[key][1].writerow(row)

    def close(self):
        """Close all open files."""
        for f, _ in self.files.values():
            f.close()
        self.files.clear()


class SpectraWriter:
    """Write spectra (FFT snapshots) to NDJSON.gz."""

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir / "spectra"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.files = {}

    def write(self, spectrum: Dict[str, Any]):
        """Write a spectrum (one JSON line per device×axis×snapshot)."""
        ts = spectrum["timestamp"]
        dt = ts.strftime("%Y-%m-%d")
        hh = ts.strftime("%H")
        part_dir = self.output_dir / f"dt={dt}" / f"hh={hh}"
        part_dir.mkdir(parents=True, exist_ok=True)

        key = (dt, hh)
        if key not in self.files:
            part_file = part_dir / f"part-{len(self.files):03d}.ndjson.gz"
            self.files[key] = gzip.open(part_file, "wt")

        ts_str = ts.strftime("%Y-%m-%dT%H:%M:%S") + f".{ts.microsecond:06d}000Z"
        row = dict(spectrum)
        row["timestamp"] = ts_str
        self.files[key].write(json.dumps(row) + "\n")

    def close(self):
        """Close all open files."""
        for f in self.files.values():
            f.close()
        self.files.clear()


class TruthLabelsWriter:
    """Write truth labels (ground truth scenarios) to CSV."""

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir / "truth"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.file = gzip.open(self.output_dir / "labels.csv.gz", "wt", newline="")
        self.writer = csv.DictWriter(self.file, fieldnames=[
            "label_id", "asset_id", "device_ID",
            "scenario", "start_ts", "functional_failure_ts", "end_ts",
            "expected_reasons",
        ])
        self.writer.writeheader()

    def write(self, label: Dict[str, Any]):
        """Write a truth label."""
        row = dict(label)
        # Format timestamps
        for ts_field in ["start_ts", "functional_failure_ts", "end_ts"]:
            if ts_field in row and row[ts_field]:
                ts = row[ts_field]
                row[ts_field] = ts.strftime("%Y-%m-%dT%H:%M:%S") + f".{ts.microsecond:06d}000Z"
        self.writer.writerow(row)

    def close(self):
        """Close file."""
        self.file.close()
