import streamlit as st
import duckdb
from pathlib import Path
import time

st.set_page_config(page_title="Waterfall", page_icon="3️⃣", layout="wide")

# Auto-refresh every 5 seconds
if "last_refresh" not in st.session_state:
    st.session_state.last_refresh = time.time()

time_since_refresh = time.time() - st.session_state.last_refresh
if time_since_refresh > 5:
    st.session_state.last_refresh = time.time()
    st.rerun()

st.title("3️⃣ Waterfall (Spectra Over Time)")

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
    devices = db.execute("SELECT DISTINCT device_id FROM raw.spectra ORDER BY device_id").fetchall()
    device_list = [row[0] for row in devices if row[0]]

    if not device_list:
        st.warning("No spectra found")
        st.stop()

    selected_device = st.selectbox("Select Device", device_list)

    # Get last 10 spectra
    spectra_list = db.execute(f"""
        SELECT timestamp, df_hz, bins
        FROM raw.spectra
        WHERE device_id = '{selected_device}'
        ORDER BY timestamp DESC
        LIMIT 10
    """).fetchall()

    if spectra_list:
        st.subheader(f"Waterfall Plot - {selected_device} (Time × Frequency × Amplitude)")

        import numpy as np
        import pandas as pd

        # Build 2D matrix: time (rows) × frequency (cols) × amplitude (values)
        waterfall_data = []
        timestamps = []

        for ts, df, bins in reversed(spectra_list):
            if bins:
                waterfall_data.append(bins)
                timestamps.append(str(ts)[:19])  # Short timestamp

        if waterfall_data:
            matrix = np.array(waterfall_data)

            # Use heatmap via plotly
            try:
                import plotly.graph_objects as go

                fig = go.Figure(data=go.Heatmap(
                    z=matrix,
                    x=np.arange(matrix.shape[1]),
                    y=timestamps,
                    colorscale='Viridis'
                ))
                fig.update_layout(
                    title=f"Spectral Waterfall - {selected_device}",
                    xaxis_title="Frequency Bin",
                    yaxis_title="Time",
                    height=500,
                    width=1000
                )
                st.plotly_chart(fig, use_container_width=True)
            except:
                st.info("Plotly not available. Showing matrix as heatmap:")
                df_heat = pd.DataFrame(matrix, index=timestamps)
                st.write(df_heat)

        st.info(f"Showing last {len(waterfall_data)} spectra in waterfall view (time progressing downward)")
    else:
        st.warning("No spectral data available")

except Exception as e:
    st.error(f"Error: {e}")
