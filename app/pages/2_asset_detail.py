import streamlit as st
import duckdb
from pathlib import Path
import time

st.set_page_config(page_title="Asset Detail", page_icon="📊", layout="wide")

# Auto-refresh every 5 seconds
if "last_refresh" not in st.session_state:
    st.session_state.last_refresh = time.time()

time_since_refresh = time.time() - st.session_state.last_refresh
if time_since_refresh > 5:
    st.session_state.last_refresh = time.time()
    st.rerun()

st.title("📊 Asset Detail")

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
    assets = db.execute("SELECT DISTINCT device_id FROM raw.vibration_frames ORDER BY device_id").fetchall()
    asset_list = [row[0] for row in assets if row[0]]

    if not asset_list:
        st.warning("No assets found")
        st.stop()

    selected_asset = st.selectbox("Select Asset", asset_list)

    col1, col2, col3 = st.columns(3)

    # Latest metrics
    latest = db.execute(f"""
        SELECT
          x_amplitude_um_pp,
          y_amplitude_um_pp,
          z_amplitude_um_pp,
          temperature_c,
          output_hz
        FROM raw.vibration_frames vf
        LEFT JOIN raw.drive_telemetry dt ON vf.device_id = dt.drive_id
        WHERE vf.device_id = '{selected_asset}'
        ORDER BY vf.timestamp DESC
        LIMIT 1
    """).fetchall()

    if latest:
        x, y, z, temp, output_hz = latest[0]
        col1.metric("X Amplitude", f"{x:.1f} µm" if x else "N/A")
        col2.metric("Y Amplitude", f"{y:.1f} µm" if y else "N/A")
        col3.metric("Z Amplitude", f"{z:.1f} µm" if z else "N/A")

        col1.metric("Temperature", f"{temp:.1f}°C" if temp else "N/A")
        col2.metric("Output Freq", f"{output_hz:.0f} Hz" if output_hz else "N/A")

    st.divider()

    # Time series
    st.subheader("Time Series (Last 100 samples)")
    ts_data = db.execute(f"""
        SELECT
          timestamp,
          x_amplitude_um_pp,
          y_amplitude_um_pp,
          z_amplitude_um_pp,
          temperature_c
        FROM raw.vibration_frames
        WHERE device_id = '{selected_asset}'
        ORDER BY timestamp DESC
        LIMIT 100
    """).fetch_df()

    if ts_data is not None and not ts_data.empty:
        ts_data = ts_data.sort_values('timestamp')
        st.line_chart(ts_data.set_index('timestamp')[['x_amplitude_um_pp', 'y_amplitude_um_pp', 'z_amplitude_um_pp']])
        st.line_chart(ts_data.set_index('timestamp')[['temperature_c']])
    else:
        st.info("No time series data")

except Exception as e:
    st.error(f"Error: {e}")
