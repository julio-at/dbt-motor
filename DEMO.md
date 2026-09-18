# 🎥 Live Demo: Motor Health Lab

**Goal:** Show live data moving visually on dashboard every 5 seconds without manual refresh.

## Setup (One Time)

```bash
# Build Docker images
docker-compose build

# Or locally: ensure Python 3.11 + dbt dependencies
uv sync
```

---

## Run Demo (3 Terminals)

### Terminal 1: Initialize Pipeline

Generates synthetic data, loads into DuckDB, builds dbt models.

```bash
make docker-init
# Or locally:
# make gen PROFILE=dev && make load && make dbt-build
```

**Expected output:**
```
✓ Generated 2.6M vibration frames
✓ Generated 435k drive telemetry rows
✓ Loaded into DuckDB
✓ Built all dbt models
```

Takes ~5–10 minutes (first time).

---

### Terminal 2: Start Dashboard

Opens Streamlit at **http://localhost:8501**

```bash
make docker-app
# Or locally: streamlit run app/streamlit_app.py
```

**Expected output:**
```
  You can now view your Streamlit app in your browser.
  Local URL: http://localhost:8501
```

Dashboard shows static data initially (from `make docker-init`).

---

### Terminal 3: Inject Live Data (Watch Metrics Update Every 5 Seconds)

```bash
make replay PROFILE=dev
# Or with custom speed:
# make replay PROFILE=dev SPEED=100x
```

**Expected output:**
```
Connected to dbt/motor_health_lab.duckdb
Loading data from data/dev...
  - 2177280 frame rows
  - 435456 drive rows
  - 18144 spectra rows
  - 2 truth rows

Replaying at 10x speed, starting 2026-01-01T00:00:00+00:00
Pausing 3s between batches so dashboard updates every ~5 seconds

Injecting vibration frames (2177280 rows)...
  Batch 1/10: 217728 rows → raw.vibration_frames
    (pausing 3s for dashboard refresh...)
  Batch 2/10: 217728 rows → raw.vibration_frames
    (pausing 3s for dashboard refresh...)
  ...
```

---

## What to Watch

### Home Page (`http://localhost:8501`)
- **Assets metric:** Shows count of unique devices (should be 12)
- **Frames metric:** ⬆️ Increases every 5 seconds as replay injects data
- **Spectra metric:** ⬆️ Increases every 5 seconds
- **Latest data timestamp:** ⬆️ Advances as new batches inject

### Plant Map (`🗺️ Plant Map` page)
- Asset amplitudes update live every 5 seconds
- Temperature values change as new frames arrive

### Asset Detail (`📊 Asset Detail` page)
- X/Y/Z amplitude line charts grow right-to-left
- Temperature curve rises/falls visibly
- Latest metrics at top refresh every 5 seconds

### Fleet (`📋 Fleet` page)
- Frame count per asset increases
- Max/min amplitudes update

---

## Speed Control

Run replay at different speeds to test performance:

```bash
# 1x real-time (slow, good for detailed observation)
make replay PROFILE=dev SPEED=1x

# 10x speed (default, smooth updates)
make replay PROFILE=dev SPEED=10x

# 100x speed (fast, for quick demo)
make replay PROFILE=dev SPEED=100x
```

Pause between batches is always 3 seconds (dashboard checks every 5s).

---

## Profiles

Use different data profiles to vary demo complexity:

- `PROFILE=dev` (default): 21 days, 12 assets, 1 frame/10s → **Fast** (~10 min setup)
- `PROFILE=demo`: 30 days, 24 assets, 1 frame/2s → **Medium** (~15 min setup)
- `PROFILE=full`: 3 days, 24 assets, 2 frames/s → **Detailed** (~20 min setup)

```bash
make gen PROFILE=demo
make load
make dbt-build
make replay PROFILE=demo SPEED=10x
```

---

## Stop Everything

```bash
# Terminal 3: Ctrl+C (stops replay)
# Terminal 2: Ctrl+C (stops Streamlit)
# Terminal 1: Ctrl+C (stops docker-compose)

# Or from any terminal:
make docker-down
```

---

## Troubleshooting

### Dashboard shows "Latest data: None"
- Replay hasn't injected any data yet. Wait for first batch.

### Metrics don't update every 5 seconds
- Check browser console for errors (F12 → Console)
- Reload page (Cmd+R / Ctrl+R)
- Ensure DuckDB file exists: `ls -l dbt/motor_health_lab.duckdb`

### Replay hangs
- Disk full? Check: `df -h`
- Database locked? Stop dashboard + restart

### Docker image not found
```bash
docker-compose build
make docker-init
```

---

## What's Happening Under the Hood

1. **Dashboard** (`app/streamlit_app.py`):
   - Every page imports `time` and checks `st.session_state.last_refresh`
   - If > 5 seconds since last refresh, calls `st.rerun()`
   - Fresh DuckDB connection on every rerun (no caching)

2. **Replay** (`app/replay.py`):
   - Loads synthetic data in partitions
   - Splits into batches (~10% of total rows per batch)
   - Injects each batch, then pauses 3 seconds
   - Timestamps are compressed (10x = 10x faster wall-clock)

3. **DuckDB**:
   - Read-only from Streamlit (no write conflicts)
   - Atomic inserts from replay (consistent reads)
   - No indices or aggregation (all queries fast)

---

## Demo Script (for presentations)

```bash
# Show: "Watch data flow live every 5 seconds"

# 1. Open Terminal 1 + Terminal 2 + Terminal 3 windows
# 2. Terminal 1: make docker-init
#    (while waiting...)
# 3. Terminal 2: make docker-app
#    (let dashboard load, point out "Frames: X" metric)
# 4. Terminal 3: make replay PROFILE=dev SPEED=100x
#    (explain: injects 10% every 3 seconds)
#
# 5. WATCH: Dashboard home page
#    "Notice Frames count increases every 5 seconds.
#     That's live data flowing in. No manual refresh needed.
#     Check Asset Detail, Spectrum, Waterfall — all updating live."
#
# 6. Switch to different pages to show live updates
# 7. Stop with Ctrl+C when done
```

---

## Questions?

- **Data too static?** Increase replay speed: `make replay SPEED=100x`
- **Need more detail?** Use `PROFILE=full` for 2 frames/sec
- **Want to understand the code?** Check `docs/SPEC.md` §10 (dashboard) and §3 (data generation)

---

**v1.0** — Live dashboard with 5-second auto-refresh. Ready for presentation. 🚀
