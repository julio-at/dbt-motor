"""Tests for data ingestion (Phase 3)."""

import pytest
import tempfile
from pathlib import Path
import duckdb


class TestDuckDBSetup:
    """Test DuckDB initialization."""

    def test_setup_creates_schemas(self):
        """Setup should create all required schemas."""
        from ingest.setup import setup

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a temporary DB
            db_path = Path(tmpdir) / "test.duckdb"

            # Monkeypatch DB_PATH
            import ingest.setup as setup_module
            original_path = setup_module.DB_PATH
            setup_module.DB_PATH = str(db_path)

            try:
                setup()

                # Verify schemas exist
                db = duckdb.connect(str(db_path))
                schemas = db.sql("SELECT schema_name FROM information_schema.schemata").fetchall()
                schema_names = [s[0] for s in schemas]

                for schema in ["RAW", "STAGING", "INTERMEDIATE", "MARTS", "EVAL", "SEEDS"]:
                    assert schema in schema_names, f"Schema {schema} not created"

                db.close()
            finally:
                setup_module.DB_PATH = original_path

    def test_setup_creates_raw_tables(self):
        """Setup should create all RAW tables."""
        from ingest.setup import setup

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.duckdb"

            import ingest.setup as setup_module
            original_path = setup_module.DB_PATH
            setup_module.DB_PATH = str(db_path)

            try:
                setup()

                db = duckdb.connect(str(db_path))
                tables = db.sql("SELECT table_name FROM information_schema.tables WHERE table_schema='RAW'").fetchall()
                table_names = [t[0] for t in tables]

                for table in ["vibration_frames", "drive_telemetry", "spectra", "truth_labels"]:
                    assert table in table_names, f"Table {table} not created"

                db.close()
            finally:
                setup_module.DB_PATH = original_path


class TestDataLoad:
    """Test data loading from generated files."""

    def test_load_frames_from_dev_profile(self):
        """Load frames from dev profile data."""
        from ingest.load import load_frames
        from ingest.setup import setup

        # Assume data/dev/ exists (from Phase 1/2)
        data_dir = Path("data/dev")
        if not data_dir.exists():
            pytest.skip("data/dev not found (run make gen PROFILE=dev first)")

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.duckdb"

            # Setup schema
            db = duckdb.connect(str(db_path))
            db.execute("CREATE SCHEMA RAW")
            db.execute("""
                CREATE TABLE RAW.vibration_frames (
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

            # Load
            frame_count = load_frames(db, data_dir)
            assert frame_count > 0, "No frames loaded"

            # Verify data
            result = db.sql("SELECT COUNT(*) as cnt FROM RAW.vibration_frames").fetchall()
            assert result[0][0] == frame_count

            db.close()

    def test_parse_timestamp(self):
        """Test ISO-8601 timestamp parsing."""
        from ingest.load import parse_timestamp

        ts_str = "2026-01-04T10:00:00.000000000Z"
        ts = parse_timestamp(ts_str)

        assert ts.year == 2026
        assert ts.month == 1
        assert ts.day == 4
        assert ts.hour == 10
        assert ts.minute == 0
        assert ts.second == 0
