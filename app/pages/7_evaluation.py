import streamlit as st
import duckdb
from pathlib import Path
import time

st.set_page_config(page_title="Evaluation", page_icon="✅", layout="wide")

# Auto-refresh every 5 seconds
if "last_refresh" not in st.session_state:
    st.session_state.last_refresh = time.time()

time_since_refresh = time.time() - st.session_state.last_refresh
if time_since_refresh > 5:
    st.session_state.last_refresh = time.time()
    st.rerun()

st.title("✅ Evaluation (Lab Only)")

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
    # Truth labels
    truth = db.execute("""
        SELECT
          label_id,
          asset_id,
          scenario,
          start_ts,
          functional_failure_ts,
          end_ts
        FROM raw.truth_labels
        ORDER BY label_id
    """).fetch_df()

    if truth is not None and not truth.empty:
        st.subheader("Synthetic Fault Scenarios")
        st.dataframe(truth, use_container_width=True, hide_index=True)

        st.divider()

        # Detection metrics (when eval model is ready)
        col1, col2 = st.columns(2)

        with col1:
            st.info(f"Total scenarios: {len(truth)}")
            st.caption("Scenarios are synthetic faults injected for model evaluation")

        with col2:
            st.info("Detection lead times: Track when rules trigger ALERT/DANGER")
            st.caption("(Populate when eval_detection model is built)")

    else:
        st.info("No truth labels (no synthetic faults for this dataset)")

except Exception as e:
    st.error(f"Error: {e}")
