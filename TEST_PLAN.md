# Motor Health Lab — Complete Test Plan

## Phase 1: Pipeline Initialization ✓

```bash
# Terminal 1: Start init pipeline (gen + ingest + dbt)
make docker-init
# Expected: 5-10 minutes, completes with "Pipeline complete"
```

**What happens:**
- Docker pulls python:3.11-slim image
- Generator creates 21 days synthetic data (12 assets, dev profile)
- Data lands in `data/` partition (dt=YYYY-MM-DD/hh=HH)
- Ingest loads 2.6M rows into DuckDB `.duckdb` file
- dbt builds: staging → intermediate → marts → eval models

**Verify:**
```bash
# Check DuckDB was created
ls -lh .duckdb

# Check row counts
python3 -c "
import duckdb
db = duckdb.connect('.duckdb', read_only=True)
print('RAW tables:')
for t in ['vibration_frames', 'drive_telemetry', 'spectra', 'truth_labels']:
    count = db.execute(f'SELECT COUNT(*) FROM raw.{t}').fetchall()[0][0]
    print(f'  {t}: {count:,}')
print('\\nMARTS tables:')
for t in ['fct_asset_health_hourly', 'dim_asset']:
    count = db.execute(f'SELECT COUNT(*) FROM marts.{t}').fetchall()[0][0]
    print(f'  {t}: {count:,}')
print('\\nEVAL tables:')
for t in ['eval_detection']:
    count = db.execute(f'SELECT COUNT(*) FROM eval.{t}').fetchall()[0][0]
    print(f'  {t}: {count:,}')
"
```

**Expected output:**
```
RAW tables:
  vibration_frames: 2,177,280
  drive_telemetry: 435,456
  spectra: 18,144
  truth_labels: 2

MARTS tables:
  fct_asset_health_hourly: 504
  dim_asset: 12

EVAL tables:
  eval_detection: 2
```

---

## Phase 2: Dashboard Startup

```bash
# Terminal 2: Start Streamlit dashboard
make docker-app
# Expected: "Streamlit running on http://localhost:8501"
```

**Open browser:**
- http://localhost:8501

**What you'll see:**
- Title: "⚙️ Motor Health Lab"
- Metrics (top): Total Assets (12), DANGER, ALERT, WATCH counts
- Navigation: 7 pages listed (Plant Map, Asset Detail, Spectrum, Waterfall, Fleet, Power, Evaluation)
- Data loaded: row counts from all RAW tables

---

## Phase 3: Data Integrity Checks

### Query 3.1: Asset Diversity

```sql
SELECT DISTINCT
  asset_type,
  poles,
  iso_group,
  foundation,
  COUNT(*) as count
FROM marts.dim_asset
GROUP BY 1, 2, 3, 4
ORDER BY asset_type, poles;
```

**Expected:**
```
asset_type | poles | iso_group | foundation | count
CNV        |     4 |         2 | RIGID      |    10
MILL       |     6 |         1 | FLEXIBLE   |     2
```

### Query 3.2: Health Status Distribution (Latest Hour)

```sql
SELECT
  overall_status,
  COUNT(*) as count
FROM marts.fct_asset_health_hourly
WHERE hour_start_ns = (SELECT MAX(hour_start_ns) FROM marts.fct_asset_health_hourly)
GROUP BY overall_status
ORDER BY overall_status;
```

**Expected:** Mix of NORMAL, WATCH, ALERT (some assets should show ALERT or DANGER due to injected faults)

### Query 3.3: Vibration Severity Zones

```sql
SELECT
  vibration_status,
  COUNT(*) as count,
  MIN(greatest(x_v_rms_p95_mm_s, y_v_rms_p95_mm_s)) as min_velocity,
  MAX(greatest(x_v_rms_p95_mm_s, y_v_rms_p95_mm_s)) as max_velocity
FROM marts.fct_asset_health_hourly
GROUP BY vibration_status
ORDER BY vibration_status;
```

**Expected:** See NORMAL/WATCH/ALERT/DANGER distributed by velocity thresholds

### Query 3.4: Detection Lead Times

```sql
SELECT
  asset_id,
  scenario,
  detected,
  lead_time_hours
FROM eval.eval_detection
ORDER BY lead_time_hours DESC NULLS LAST;
```

**Expected:** See which synthetic faults were detected and how far in advance (hours)

---

## Phase 4: Physics Validation

### Check: Velocity RMS Formula

```sql
-- Verify SPEC §4.1 formula: v_rms = 2.2214e-3 * f_1x * d_pp_um
SELECT
  device_id,
  timestamp_ns,
  f_1x_hz,
  x_d_pp_um,
  x_v_rms_mm_s,
  (2.2214e-3 * f_1x_hz * x_d_pp_um) as expected_v_rms,
  ABS((2.2214e-3 * f_1x_hz * x_d_pp_um) - x_v_rms_mm_s) / x_v_rms_mm_s as error_pct
FROM intermediate.int_frames_enriched
LIMIT 10;
```

**Expected:** error_pct < 0.001 (≤0.1%) for all rows

### Check: Running Speed Calculation

```sql
-- Verify shaft frequency = motor_speed_rpm / 60
SELECT
  device_id,
  motor_speed_rpm,
  f_1x_hz,
  motor_speed_rpm / 60.0 as expected_f_1x,
  ABS((motor_speed_rpm / 60.0) - f_1x_hz) as error_hz
FROM intermediate.int_frames_enriched
WHERE motor_speed_rpm IS NOT NULL
LIMIT 10;
```

**Expected:** error_hz < 0.01 (negligible, quantization only)

---

## Phase 5: Replay Engine (Optional Live Demo)

```bash
# Terminal 3: Start replay (time-stepped injection)
make docker-replay
# Expected: "Replaying at 10x speed, starting 2026-01-01T00:00:00Z"
#          Batch by batch, dashboard updates every 2 seconds
```

**While running:**
- Watch dashboard refresh in real-time
- Status changes as data flows in
- Metrics and rows update live

**Stop:** Ctrl+C in terminal 3

---

## Phase 6: Full Integration Test (All-In-One)

```bash
# Teardown
make docker-down

# Clean slate
make clean

# Full pipeline
make docker-init && make docker-app
```

**Expected:** Dashboard ready with fresh data in <10 minutes

---

## Phase 7: Local Development (No Docker)

```bash
# If you want to iterate locally without Docker:
uv sync
make init-db
make gen PROFILE=dev
make load
make dbt-build
make app  # Opens http://localhost:8501 locally
```

---

## Test Summary Checklist

- [ ] **Init:** docker-init completes, 2.6M rows in DuckDB
- [ ] **Dashboard:** http://localhost:8501 loads, shows metrics
- [ ] **Assets:** 12 assets (10 conveyor 4-pole, 2 mill 6-pole) visible
- [ ] **Health Status:** Mix of NORMAL/WATCH/ALERT seen in latest hour
- [ ] **Physics:** Velocity RMS formula validated (error < 0.1%)
- [ ] **Detection:** Truth labels show lead times
- [ ] **Replay:** Live data injection works (optional)
- [ ] **Local:** make gen + make load + make app works without Docker

**All pass? Motor Health Lab is 100% functional. Ready for production training.** 🚀
