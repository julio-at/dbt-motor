import streamlit as st
import duckdb
from pathlib import Path
import json
import time

st.set_page_config(page_title="Spectrum", page_icon="📈", layout="wide")

# Auto-refresh every 5 seconds
if "last_refresh" not in st.session_state:
    st.session_state.last_refresh = time.time()

time_since_refresh = time.time() - st.session_state.last_refresh
if time_since_refresh > 5:
    st.session_state.last_refresh = time.time()
    st.rerun()

st.title("📈 Spectrum (FFT)")

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

    # Get latest spectrum
    spectrum_raw = db.execute(f"""
        SELECT
          axis,
          f_max_hz,
          df_hz,
          bins
        FROM raw.spectra
        WHERE device_id = '{selected_device}'
        ORDER BY timestamp DESC
        LIMIT 1
    """).fetchall()

    if spectrum_raw:
        axis, f_max, df, bins = spectrum_raw[0]

        st.subheader(f"FFT Spectrum - {selected_device} ({axis} axis)")

        col1, col2, col3 = st.columns(3)
        col1.metric("Max Freq", f"{f_max:.0f} Hz")
        col2.metric("Freq Resolution", f"{df:.2f} Hz/bin")
        col3.metric("Bins", len(bins) if bins else 0)

        if bins:
            import numpy as np
            freqs = np.arange(len(bins)) * df
            import pandas as pd
            spec_df = pd.DataFrame({
                "Frequency (Hz)": freqs,
                "Amplitude": bins
            })
            st.bar_chart(spec_df.set_index("Frequency (Hz)"), use_container_width=True, height=400)
        else:
            st.info("No FFT data available")
    else:
        st.warning(f"No spectrum data for {selected_device}")

except Exception as e:
    st.error(f"Error: {e}")
