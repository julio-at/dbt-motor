"""
Data replay engine — inject timestamped data into DuckDB for live dashboard demos.

Controls clock speed and injects data in batches with pauses so the dashboard
can show live updates every 5 seconds.

Usage:
    python app/replay.py --speed 10x --start-time 2026-01-01 --pause 3
"""

import argparse
import time
from datetime import datetime
from pathlib import Path
import gzip
import json
import duckdb
import pandas as pd
import sys

def load_replay_data(data_dir: Path) -> dict:
    """Load synthetic data partitions in chronological order."""
    frames, drive, spectra, truth = [], [], [], []

    # Try both structures: dt=*/hh=* (flat) and frames/dt=*/hh=* (nested)
    dt_pattern = (
        list(data_dir.glob("dt=*/hh=*")) or
        list(data_dir.glob("frames/dt=*/hh=*"))
    )

    # Sort by partition (dt/hh)
    for dt_hh in sorted(dt_pattern):
        try:
            dt_str = (
                [p for p in dt_hh.parts if p.startswith("dt=")][0].split("=")[1]
            )
            hh_str = (
                [p for p in dt_hh.parts if p.startswith("hh=")][0].split("=")[1]
            )

            # Load CSVs
            for f in dt_hh.glob("part-*.csv.gz"):
                frames.append(pd.read_csv(f, compression="gzip"))
            for f in dt_hh.glob("drive_*.csv.gz"):
                drive.append(pd.read_csv(f, compression="gzip"))
            for f in dt_hh.glob("spectra_*.ndjson.gz"):
                with gzip.open(f, "rt") as fh:
                    lines = [json.loads(line) for line in fh if line.strip()]
                    if lines:
                        spectra.append(pd.DataFrame(lines))
        except Exception:  # noqa: E722
            pass

    # Truth labels
    truth_paths = (
        list(data_dir.glob("truth/labels.csv.gz")) +
        list(data_dir.glob("truth_labels.ndjson.gz"))
    )
    for truth_path in truth_paths:
        if truth_path.exists():
            try:
                if str(truth_path).endswith(".csv.gz"):
                    df = pd.read_csv(truth_path, compression="gzip")
                    if not df.empty:
                        truth.append(df)
                else:
                    with gzip.open(truth_path, "rt") as fh:
                        lines = [
                            json.loads(line) for line in fh if line.strip()
                        ]
                        if lines:
                            truth.append(pd.DataFrame(lines))
            except Exception:  # noqa: E722
                pass

    return {
        "frames": pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(),
        "drive": pd.concat(drive, ignore_index=True) if drive else pd.DataFrame(),
        "spectra": pd.concat(spectra, ignore_index=True) if spectra else pd.DataFrame(),
        "truth": pd.concat(truth, ignore_index=True) if truth else pd.DataFrame(),
    }

def inject_batch(
    db: duckdb.DuckDBPyConnection,
    table: str,
    df: pd.DataFrame,
    start_time: datetime,
    compression: float = 1.0,
):
    """
    Inject data with time adjustment and compression.

    Args:
        db: DuckDB connection
        table: Target table name
        df: DataFrame to insert
        start_time: Replay start time
        compression: Time compression (10x = 10x faster)
    """
    if df.empty:
        return

    df_copy = df.copy()

    # Parse original timestamps and compute offset
    if "timestamp_ns" in df_copy.columns:
        min_ts = pd.to_datetime(df_copy["timestamp_ns"]).min()
        df_copy["timestamp_ns"] = (
            (pd.to_datetime(df_copy["timestamp_ns"]) - min_ts) / compression
            + pd.Timestamp(start_time, tz="UTC")
        ).astype("int64")

    # Add metadata columns if missing
    if "_file_name" not in df_copy.columns:
        df_copy["_file_name"] = "replay"
    if "_file_row" not in df_copy.columns:
        df_copy["_file_row"] = range(len(df_copy))
    if "_loaded_at" not in df_copy.columns:
        df_copy["_loaded_at"] = pd.Timestamp.now(tz="UTC")

    # Insert
    db.from_df(df_copy).insert_into(f"raw.{table}")
    print(f"✓ Inserted {len(df_copy)} rows into raw.{table}")

def inject_in_batches(
    db: duckdb.DuckDBPyConnection,
    table: str,
    df: pd.DataFrame,
    start_time: datetime,
    compression: float = 1.0,
    pause_sec: float = 3.0,
    batch_size: int = None,
):
    """
    Inject data in batches with pauses so dashboard can show live updates.

    Args:
        db: DuckDB connection
        table: Target table name
        df: Full DataFrame to insert
        start_time: Replay start time
        compression: Time compression
        pause_sec: Pause between batches (seconds)
        batch_size: Rows per batch (default: 1/10 of total)
    """
    if df.empty:
        return

    # Determine batch size
    if batch_size is None:
        batch_size = max(100, len(df) // 10)

    df_copy = df.copy()

    # Parse original timestamps and compute offset
    if "timestamp_ns" in df_copy.columns:
        min_ts = pd.to_datetime(df_copy["timestamp_ns"]).min()
        df_copy["timestamp_ns"] = (
            (pd.to_datetime(df_copy["timestamp_ns"]) - min_ts) / compression
            + pd.Timestamp(start_time, tz="UTC")
        ).astype("int64")

    # Add metadata columns if missing
    if "_file_name" not in df_copy.columns:
        df_copy["_file_name"] = "replay"
    if "_file_row" not in df_copy.columns:
        df_copy["_file_row"] = range(len(df_copy))
    if "_loaded_at" not in df_copy.columns:
        df_copy["_loaded_at"] = pd.Timestamp.now(tz="UTC")

    # Inject in batches
    total_batches = (len(df_copy) + batch_size - 1) // batch_size
    for i in range(0, len(df_copy), batch_size):
        batch = df_copy.iloc[i:i+batch_size]
        db.from_df(batch).insert_into(f"raw.{table}")
        batch_num = (i // batch_size) + 1
        print(f"  Batch {batch_num}/{total_batches}: {len(batch)} rows → raw.{table}")
        sys.stdout.flush()

        # Pause between batches (except after the last one)
        if i + batch_size < len(df_copy) and pause_sec > 0:
            print(f"    (pausing {pause_sec}s for dashboard refresh...)")
            sys.stdout.flush()
            time.sleep(pause_sec)

def main():
    parser = argparse.ArgumentParser(description="Replay synthetic data with live dashboard updates.")
    parser.add_argument("--data-dir", type=Path, default=Path("data"), help="Data partition directory")
    parser.add_argument("--db-path", type=Path, default=Path(".duckdb"), help="DuckDB path")
    parser.add_argument("--speed", default="1x", help="Replay speed (1x, 10x, 100x)")
    parser.add_argument("--start-time", help="Start time ISO8601 (default: 2026-01-01T00:00:00Z)")
    parser.add_argument("--pause", type=float, default=3, help="Pause between batches (seconds, default 3)")
    parser.add_argument("--batch-size", type=int, help="Rows per batch (default: 1/10 of total)")
    parser.add_argument("--clear", action="store_true", help="Clear RAW tables before replay")
    args = parser.parse_args()

    # Defaults
    if not args.start_time:
        args.start_time = "2026-01-01T00:00:00Z"
    start_time = datetime.fromisoformat(args.start_time.replace("Z", "+00:00"))
    compression = float(args.speed.replace("x", ""))

    # Connect
    db = duckdb.connect(str(args.db_path))
    print(f"Connected to {args.db_path}")

    # Clear if requested
    if args.clear:
        for table in ["vibration_frames", "drive_telemetry", "spectra", "truth_labels"]:
            db.execute(f"DELETE FROM raw.{table}")
            print(f"✓ Cleared raw.{table}")

    # Load data
    print(f"Loading data from {args.data_dir}...")
    data = load_replay_data(args.data_dir)
    print(f"  - {len(data['frames'])} frame rows")
    print(f"  - {len(data['drive'])} drive rows")
    print(f"  - {len(data['spectra'])} spectra rows")
    print(f"  - {len(data['truth'])} truth rows")

    # Inject with batches and pauses
    print(f"\nReplaying at {args.speed} speed, starting {start_time}")
    print(f"Pausing {args.pause}s between batches so dashboard updates every ~5 seconds\n")

    # Inject frames in batches with pauses
    if not data["frames"].empty:
        print(f"Injecting vibration frames ({len(data['frames'])} rows)...")
        inject_in_batches(db, "vibration_frames", data["frames"], start_time, compression, args.pause, args.batch_size)

    # Inject drive telemetry in batches
    if not data["drive"].empty:
        print(f"\nInjecting drive telemetry ({len(data['drive'])} rows)...")
        inject_in_batches(db, "drive_telemetry", data["drive"], start_time, compression, args.pause, args.batch_size)

    # Inject spectra in batches
    if not data["spectra"].empty:
        print(f"\nInjecting spectra ({len(data['spectra'])} rows)...")
        inject_in_batches(db, "spectra", data["spectra"], start_time, compression, args.pause, args.batch_size)

    # Truth labels (one-shot, no pause needed)
    if not data["truth"].empty:
        print(f"\nInjecting truth labels ({len(data['truth'])} rows)...")
        inject_batch(db, "truth_labels", data["truth"], start_time, compression=1.0)

    print("\n✓ Replay complete! Dashboard is now live with data.")
    print("  → Open in browser: streamlit run app/streamlit_app.py")
    print("  → Data updates every 5 seconds as batches inject")

if __name__ == "__main__":
    main()
