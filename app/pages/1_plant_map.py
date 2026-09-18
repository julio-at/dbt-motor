import streamlit as st
import duckdb
from pathlib import Path
import re
import time

st.set_page_config(page_title="Plant Map", page_icon="🗺️", layout="wide")

# Auto-refresh every 5 seconds
if "last_refresh" not in st.session_state:
    st.session_state.last_refresh = time.time()

time_since_refresh = time.time() - st.session_state.last_refresh
if time_since_refresh > 5:
    st.session_state.last_refresh = time.time()
    st.rerun()

st.title("🗺️ Plant Map")

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
    # Get latest vibration data per device
    data = db.execute("""
        SELECT
          device_id,
          coordinates_position,
          x_amplitude_um_pp,
          y_amplitude_um_pp,
          temperature_c
        FROM raw.vibration_frames
        WHERE device_id IS NOT NULL
        ORDER BY timestamp DESC
        LIMIT 100
    """).fetch_df()

    st.markdown("### PLANT-A Layout (Floor × Tandem × Position)")

    if data is not None and not data.empty:
        for device in data['device_id'].unique()[:12]:
            device_data = data[data['device_id'] == device].iloc[0]

            # Parse coordinates_position "[floor,tandem,order]"
            coords = device_data['coordinates_position']
            try:
                parts = re.findall(r'\d+', coords)
                floor, tandem, pos = int(parts[0]), int(parts[1]), int(parts[2])
            except:
                floor, tandem, pos = 0, 0, 0

            col1, col2, col3 = st.columns([2, 1, 1])
            with col1:
                st.write(f"**Floor {floor} | Tandem {tandem} | Pos {pos}**")
            with col2:
                x_amp = device_data['x_amplitude_um_pp'] or 0
                y_amp = device_data['y_amplitude_um_pp'] or 0
                st.metric("Amplitude", f"{max(x_amp, y_amp):.0f} µm")
            with col3:
                temp = device_data['temperature_c'] or 0
                st.metric("Temp", f"{temp:.0f}°C")
            st.divider()
    else:
        st.info("No data available")

except Exception as e:
    st.error(f"Error: {e}")
