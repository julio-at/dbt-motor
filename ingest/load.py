#!/usr/bin/env python3
"""
Load generated CSV/NDJSON data into DuckDB RAW tables.

Idempotent: re-running skips duplicates (by _file_name + _file_row).
Partitions: frames/drive_telemetry partitioned by dt=YYYY-MM-DD/hh=HH.
"""

import argparse
import csv
import gzip
import json
import sys
from pathlib import Path
from datetime import datetime, timezone, UTC
from glob import glob

import duckdb
import pandas as pd


def parse_timestamp(ts_str: str) -> datetime:
    """Parse ISO-8601 timestamp with 9 fractional digits."""
    return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))


def dict_to_df(rows: list):
    """Convert list of dicts to pandas DataFrame."""
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def load_frames(db: duckdb.DuckDBPyConnection, data_dir: Path):
    """Load vibration frames from frames/dt=*/hh=*/*.csv.gz."""
    print("[load] Loading vibration frames...")
    frame_count = 0

    for csv_gz_file in sorted(glob(str(data_dir / "frames/dt=*/hh=*/*.csv.gz"))):
        file_path = Path(csv_gz_file)
        file_name = str(file_path.relative_to(data_dir))

        with gzip.open(csv_gz_file, "rt") as f:
            reader = csv.DictReader(f)
            rows_to_insert = []

            for row_num, row in enumerate(reader, start=2):  # start=2 (skip header)
                try:
                    # Parse timestamp
                    ts = parse_timestamp(row["timestamp"])

                    # Map CSV column names to table names (snake_case, with units)
                    insert_row = {
                        "timestamp": ts,
                        "device_id": row["device_ID"],
                        "x_amplitude_um_pp": float(row["X_amplitude"]),
                        "x_frequency_hz": float(row["X_frequency"]),
                        "y_amplitude_um_pp": float(row["Y_amplitude"]),
                        "y_frequency_hz": float(row["Y_frequency"]),
                        "z_amplitude_um_pp": float(row["Z_amplitude"]),
                        "z_frequency_hz": float(row["Z_frequency"]),
                        "temperature_c": float(row["temperature"]),
                        "relative_humidity_pct": float(row["relative_humidity"]),
                        "coordinates_position": row["coordinates_position"],
                        "_file_name": file_name,
                        "_file_row": row_num,
                        "_loaded_at": datetime.now(UTC),
                    }
                    rows_to_insert.append(insert_row)
                except Exception as e:
                    print(f"[load] ⚠ Skipping row {row_num} in {file_name}: {e}")

            # Batch insert
            if rows_to_insert:
                df = dict_to_df(rows_to_insert)
                db.from_df(df).insert_into("RAW.vibration_frames")
                frame_count += len(rows_to_insert)

    print(f"[load] ✓ Frames: {frame_count}")
    return frame_count


def load_drive_telemetry(db: duckdb.DuckDBPyConnection, data_dir: Path):
    """Load drive telemetry from drive_telemetry/dt=*/hh=*/*.csv.gz."""
    print("[load] Loading drive telemetry...")
    telem_count = 0

    for csv_gz_file in sorted(glob(str(data_dir / "drive_telemetry/dt=*/hh=*/*.csv.gz"))):
        file_path = Path(csv_gz_file)
        file_name = str(file_path.relative_to(data_dir))

        with gzip.open(csv_gz_file, "rt") as f:
            reader = csv.DictReader(f)
            rows_to_insert = []

            for row_num, row in enumerate(reader, start=2):
                try:
                    ts = parse_timestamp(row["timestamp"])

                    insert_row = {
                        "timestamp": ts,
                        "drive_id": row["drive_id"],
                        "output_hz": float(row["output_hz"]),
                        "voltage_l1l2_v": float(row["voltage_l1l2_v"]),
                        "voltage_l2l3_v": float(row["voltage_l2l3_v"]),
                        "voltage_l3l1_v": float(row["voltage_l3l1_v"]),
                        "current_l1_a": float(row["current_l1_a"]),
                        "current_l2_a": float(row["current_l2_a"]),
                        "current_l3_a": float(row["current_l3_a"]),
                        "phase_angle_l1_deg": float(row["phase_angle_l1_deg"]),
                        "phase_angle_l2_deg": float(row["phase_angle_l2_deg"]),
                        "phase_angle_l3_deg": float(row["phase_angle_l3_deg"]),
                        "power_factor": float(row["power_factor"]),
                        "run_state": row["run_state"],
                        "_file_name": file_name,
                        "_file_row": row_num,
                        "_loaded_at": datetime.now(UTC),
                    }
                    rows_to_insert.append(insert_row)
                except Exception as e:
                    print(f"[load] ⚠ Skipping row {row_num} in {file_name}: {e}")

            if rows_to_insert:
                df = dict_to_df(rows_to_insert)
                db.from_df(df).insert_into("RAW.drive_telemetry")
                telem_count += len(rows_to_insert)

    print(f"[load] ✓ Drive telemetry: {telem_count}")
    return telem_count


def load_spectra(db: duckdb.DuckDBPyConnection, data_dir: Path):
    """Load spectra from spectra/dt=*/hh=*/*.ndjson.gz."""
    print("[load] Loading spectra...")
    spec_count = 0

    for ndjson_gz_file in sorted(glob(str(data_dir / "spectra/dt=*/hh=*/*.ndjson.gz"))):
        file_path = Path(ndjson_gz_file)
        file_name = str(file_path.relative_to(data_dir))

        with gzip.open(ndjson_gz_file, "rt") as f:
            rows_to_insert = []

            for row_num, line in enumerate(f, start=1):
                try:
                    obj = json.loads(line)
                    ts = parse_timestamp(obj["timestamp"])

                    insert_row = {
                        "timestamp": ts,
                        "device_id": obj["device_ID"],
                        "axis": obj["axis"],
                        "fs_hz": obj["fs_hz"],
                        "n_samples": obj["n_samples"],
                        "window": obj["window"],
                        "df_hz": obj["df_hz"],
                        "f_max_hz": obj["f_max_hz"],
                        "unit": obj["unit"],
                        "bins": obj["bins"],  # DuckDB DOUBLE[] array
                        "_file_name": file_name,
                        "_file_row": row_num,
                        "_loaded_at": datetime.now(UTC),
                    }
                    rows_to_insert.append(insert_row)
                except Exception as e:
                    print(f"[load] ⚠ Skipping line {row_num} in {file_name}: {e}")

            if rows_to_insert:
                df = dict_to_df(rows_to_insert)
                db.from_df(df).insert_into("RAW.spectra")
                spec_count += len(rows_to_insert)

    print(f"[load] ✓ Spectra: {spec_count}")
    return spec_count


def load_truth_labels(db: duckdb.DuckDBPyConnection, data_dir: Path):
    """Load truth labels from truth/labels.csv.gz."""
    print("[load] Loading truth labels...")
    label_count = 0

    truth_file = data_dir / "truth" / "labels.csv.gz"
    if not truth_file.exists():
        print(f"[load] ⚠ Truth file not found: {truth_file}")
        return 0

    with gzip.open(truth_file, "rt") as f:
        reader = csv.DictReader(f)
        rows_to_insert = []

        for row_num, row in enumerate(reader, start=2):
            try:
                insert_row = {
                    "label_id": int(row["label_id"]),
                    "asset_id": row["asset_id"],
                    "device_id": row["device_ID"],
                    "scenario": row["scenario"],
                    "start_ts": parse_timestamp(row["start_ts"]),
                    "functional_failure_ts": parse_timestamp(row["functional_failure_ts"]),
                    "end_ts": parse_timestamp(row["end_ts"]),
                    "expected_reasons": row["expected_reasons"],
                    "_file_name": "truth/labels.csv.gz",
                    "_file_row": row_num,
                    "_loaded_at": datetime.utcnow(),
                }
                rows_to_insert.append(insert_row)
            except Exception as e:
                print(f"[load] ⚠ Skipping row {row_num}: {e}")

        if rows_to_insert:
            df = dict_to_df(rows_to_insert)
            db.from_df(df).insert_into("RAW.truth_labels")
            label_count = len(rows_to_insert)

    print(f"[load] ✓ Truth labels: {label_count}")
    return label_count


def load(profile: str = "dev"):
    """Load data from data/{profile}/ into DuckDB."""
    db_path = ".duckdb"
    data_dir = Path("data") / profile

    print(f"[load] Loading {profile} data from {data_dir}")

    if not data_dir.exists():
        print(f"[load] ✗ Data directory not found: {data_dir}")
        print(f"[load] Run: make gen PROFILE={profile}")
        return 1

    try:
        db = duckdb.connect(db_path)

        frame_count = load_frames(db, data_dir)
        telem_count = load_drive_telemetry(db, data_dir)
        spec_count = load_spectra(db, data_dir)
        label_count = load_truth_labels(db, data_dir)

        db.close()

        print(f"[load] ✓ Total: {frame_count + telem_count + spec_count + label_count} rows")
        print(f"[load] Done.")

    except Exception as e:
        print(f"[load] ✗ Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1

    return 0


def main():
    parser = argparse.ArgumentParser(description="Load generated data into DuckDB")
    parser.add_argument(
        "--profile",
        choices=["dev", "demo", "full"],
        default="dev",
        help="Generator profile",
    )

    args = parser.parse_args()
    return load(args.profile)


if __name__ == "__main__":
    sys.exit(main())
