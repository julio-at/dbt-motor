#!/usr/bin/env python3
"""
Initialize DuckDB and create schemas.

Schemas:
- RAW: vibration_frames, drive_telemetry, spectra
- STAGING, INTERMEDIATE, MARTS, EVAL: for dbt models
- SEEDS: static reference data
"""

import duckdb
import sys

DB_PATH = ".duckdb"


def setup():
    """Create DuckDB file and schemas."""
    print(f"[setup] Creating DuckDB at {DB_PATH}")
    db = duckdb.connect(DB_PATH)

    # Create schemas
    for schema in ["RAW", "STAGING", "INTERMEDIATE", "MARTS", "EVAL", "SEEDS"]:
        db.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
        print(f"[setup] ✓ Schema {schema}")

    # RAW.vibration_frames (from frames/dt=*/hh=*/*.csv.gz)
    db.execute("""
        CREATE TABLE IF NOT EXISTS RAW.vibration_frames (
            timestamp TIMESTAMP_NS,
            device_id VARCHAR,
            x_amplitude_um_pp DOUBLE,
            x_frequency_hz DOUBLE,
            y_amplitude_um_pp DOUBLE,
            y_frequency_hz DOUBLE,
            z_amplitude_um_pp DOUBLE,
            z_frequency_hz DOUBLE,
            temperature_c DOUBLE,
            relative_humidity_pct DOUBLE,
            coordinates_position VARCHAR,
            _file_name VARCHAR,
            _file_row INTEGER,
            _loaded_at TIMESTAMP_NS
        )
    """)
    print("[setup] ✓ Table RAW.vibration_frames")

    # RAW.drive_telemetry
    db.execute("""
        CREATE TABLE IF NOT EXISTS RAW.drive_telemetry (
            timestamp TIMESTAMP_NS,
            drive_id VARCHAR,
            output_hz DOUBLE,
            voltage_l1l2_v DOUBLE,
            voltage_l2l3_v DOUBLE,
            voltage_l3l1_v DOUBLE,
            current_l1_a DOUBLE,
            current_l2_a DOUBLE,
            current_l3_a DOUBLE,
            phase_angle_l1_deg DOUBLE,
            phase_angle_l2_deg DOUBLE,
            phase_angle_l3_deg DOUBLE,
            power_factor DOUBLE,
            run_state VARCHAR,
            _file_name VARCHAR,
            _file_row INTEGER,
            _loaded_at TIMESTAMP_NS
        )
    """)
    print("[setup] ✓ Table RAW.drive_telemetry")

    # RAW.spectra (from spectra/dt=*/hh=*/*.ndjson.gz)
    db.execute("""
        CREATE TABLE IF NOT EXISTS RAW.spectra (
            timestamp TIMESTAMP_NS,
            device_id VARCHAR,
            axis VARCHAR,
            fs_hz DOUBLE,
            n_samples INTEGER,
            "window" VARCHAR,
            df_hz DOUBLE,
            f_max_hz DOUBLE,
            unit VARCHAR,
            bins DOUBLE[],
            _file_name VARCHAR,
            _file_row INTEGER,
            _loaded_at TIMESTAMP_NS
        )
    """)
    print("[setup] ✓ Table RAW.spectra")

    # RAW.truth_labels (from truth/labels.csv.gz)
    db.execute("""
        CREATE TABLE IF NOT EXISTS RAW.truth_labels (
            label_id INTEGER,
            asset_id VARCHAR,
            device_id VARCHAR,
            scenario VARCHAR,
            start_ts TIMESTAMP_NS,
            functional_failure_ts TIMESTAMP_NS,
            end_ts TIMESTAMP_NS,
            expected_reasons VARCHAR,
            _file_name VARCHAR,
            _file_row INTEGER,
            _loaded_at TIMESTAMP_NS
        )
    """)
    print("[setup] ✓ Table RAW.truth_labels")

    db.close()
    print("[setup] ✓ DuckDB initialized")
    return 0


if __name__ == "__main__":
    sys.exit(setup())
