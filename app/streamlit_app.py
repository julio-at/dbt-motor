import streamlit as st
import duckdb
from pathlib import Path
import time

st.set_page_config(page_title="Motor Health Lab", page_icon="⚙️", layout="wide")

# Auto-refresh every 5 seconds
if "last_refresh" not in st.session_state:
    st.session_state.last_refresh = time.time()

time_since_refresh = time.time() - st.session_state.last_refresh
if time_since_refresh > 5:
    st.session_state.last_refresh = time.time()
    st.rerun()

st.title("⚙️ Motor Health Lab")

# Find DuckDB file
db_path = Path("dbt/motor_health_lab.duckdb") if Path("dbt/motor_health_lab.duckdb").exists() else None
if not db_path:
    for p in [Path("motor_health_lab.duckdb"), Path(".duckdb")]:
        if p.exists():
            db_path = p
            break

if db_path:
    try:
        # Fresh connection every refresh (no cache)
        db = duckdb.connect(str(db_path), read_only=True)

        col1, col2, col3 = st.columns(3)

        # Count assets
        assets = db.execute("SELECT COUNT(DISTINCT device_id) FROM raw.vibration_frames").fetchall()[0][0]
        col1.metric("Assets", assets)

        # Count frames (THIS UPDATES EVERY 5 SECONDS)
        frames = db.execute("SELECT COUNT(*) FROM raw.vibration_frames").fetchall()[0][0]
        col2.metric("Frames", f"{frames:,}")

        # Count spectra
        spectra = db.execute("SELECT COUNT(*) FROM raw.spectra").fetchall()[0][0]
        col3.metric("Spectra", f"{spectra:,}")

        # Latest data timestamp
        latest = db.execute("SELECT MAX(timestamp) FROM raw.vibration_frames").fetchall()[0][0]
        st.info(f"Latest data: {latest}")

        st.markdown("---")
        st.success("✅ Dashboard updating every 5 seconds")

    except Exception as e:
        st.error(f"Database error: {e}")
else:
    st.error("DuckDB file not found")
