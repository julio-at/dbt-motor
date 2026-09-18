import streamlit as st
import duckdb
from pathlib import Path
import time

st.set_page_config(page_title="Fleet", page_icon="📋", layout="wide")

# Auto-refresh every 5 seconds
if "last_refresh" not in st.session_state:
    st.session_state.last_refresh = time.time()

time_since_refresh = time.time() - st.session_state.last_refresh
if time_since_refresh > 5:
    st.session_state.last_refresh = time.time()
    st.rerun()

st.title("📋 Fleet Status")

db_path = None
for p in [Path("dbt/motor_health_lab.duckdb"), Path("motor_health_lab.duckdb"), Path(".duckdb")]:
    if p.exists():
        db_path = p
        break

if not db_path:
    st.error("DuckDB not found")
    st.stop()

db = duckdb.connect(str(db_path), read_only=True)

try:
    fleet = db.execute("""
        SELECT
          device_id,
          COUNT(*) as frame_count,
          AVG(temperature_c) as avg_temp,
          MAX(temperature_c) as max_temp,
          MIN(x_amplitude_um_pp) as min_x_um,
          MAX(x_amplitude_um_pp) as max_x_um
        FROM raw.vibration_frames
        WHERE device_id IS NOT NULL
        GROUP BY device_id
        ORDER BY device_id
    """).fetch_df()

    st.subheader("All Assets")
    st.dataframe(
        fleet,
        use_container_width=True,
        hide_index=True,
        column_config={
            "device_id": st.column_config.TextColumn("Device ID", width="medium"),
            "frame_count": st.column_config.NumberColumn("Frames", format="%d"),
            "avg_temp": st.column_config.NumberColumn("Avg Temp (°C)", format="%.1f"),
            "max_temp": st.column_config.NumberColumn("Max Temp (°C)", format="%.1f"),
            "min_x_um": st.column_config.NumberColumn("Min Amplitude (µm)", format="%.0f"),
            "max_x_um": st.column_config.NumberColumn("Max Amplitude (µm)", format="%.0f"),
        }
    )

    st.info(f"Total assets: {len(fleet)}")

except Exception as e:
    st.error(f"Error: {e}")
