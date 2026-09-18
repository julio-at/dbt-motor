import streamlit as st
import duckdb
from pathlib import Path
import time

st.set_page_config(page_title="Power", page_icon="⚡", layout="wide")

# Auto-refresh every 5 seconds
if "last_refresh" not in st.session_state:
    st.session_state.last_refresh = time.time()

time_since_refresh = time.time() - st.session_state.last_refresh
if time_since_refresh > 5:
    st.session_state.last_refresh = time.time()
    st.rerun()

st.title("⚡ Electrical Power")

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
    # Power factor summary
    pf_data = db.execute("""
        SELECT
          drive_id,
          AVG(power_factor) as avg_pf,
          COUNT(*) as samples
        FROM raw.drive_telemetry
        WHERE power_factor > 0
        GROUP BY drive_id
        ORDER BY drive_id
    """).fetch_df()

    if pf_data is not None and not pf_data.empty:
        col1, col2, col3 = st.columns(3)

        col1.metric("Avg Power Factor", f"{pf_data['avg_pf'].mean():.3f}")
        col2.metric("Min PF", f"{pf_data['avg_pf'].min():.3f}")
        col3.metric("Max PF", f"{pf_data['avg_pf'].max():.3f}")

        st.subheader("Power Factor by Drive")
        st.bar_chart(pf_data.set_index('drive_id')['avg_pf'], use_container_width=True)

        st.divider()

        # Voltage and current
        power_data = db.execute("""
            SELECT
              drive_id,
              AVG(voltage_l1l2_v) as avg_voltage,
              AVG(current_l1_a) as avg_current,
              AVG(power_factor) as power_factor,
              COUNT(*) as samples
            FROM raw.drive_telemetry
            WHERE voltage_l1l2_v > 0 AND current_l1_a > 0
            GROUP BY drive_id
            ORDER BY drive_id
        """).fetch_df()

        st.subheader("Electrical Metrics")
        st.dataframe(power_data, use_container_width=True, hide_index=True)

    else:
        st.warning("No power telemetry data available")

except Exception as e:
    st.error(f"Error: {e}")
