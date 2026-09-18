# SPEC — motor-health-lab

Status: v1.0 (local, DuckDB). Owner: Julio. Section numbers referenced by CLAUDE.md and phase prompts.

---

## 1. Purpose and scope

**Educational learning lab** demonstrating condition monitoring for industrial motors (conveyors,
mill drives). End-to-end architecture: synthetic sensor data → dbt transforms → rule-based health
evaluation → Streamlit dashboard. Everything runs locally in Docker Compose, free, reproducible,
controlled.

Target audience: engineers learning dbt, analytics engineering, condition monitoring, or building
similar systems. **Not production.** A reference implementation: "here's how you'd do this."

**In scope:**
- Synthetic data generator (Python, numpy, deterministic)
- DuckDB embedded database (zero-config local analytics)
- dbt transformations (staging → intermediate → marts)
- Health rules engine with versioned thresholds (§8)
- Evaluation framework (compare rules vs truth labels)
- Streamlit dashboard (open source, Docker)
- Data replay engine (time-stepped injection for live demos)
- GitHub Actions CI (lint, test, build)

**Out of scope (v1):**
- ML models, forecasting, clustering
- Real-time streaming (Kafka, Pub/Sub)
- Multi-tenancy, RBAC, enterprise auth
- External APIs, multi-plant federation
- The six IMU parameters (§13)
- Alerts/notifications (can add as extension)

---

## 2. Architecture

```
┌─ generator ──CSV/NDJSON──┐
│                          │
└──────► data/ (git-ignored)
         │
         ├── frames/dt=YYYY-MM-DD/hh=HH/part-*.csv.gz
         ├── drive_telemetry/...
         └── spectra/...
         
         │
         ▼
       Python ingest script
       │
       ▼
    DuckDB (.duckdb file, git-ignored)
       │
       ├─ RAW.vibration_frames
       ├─ RAW.drive_telemetry
       ├─ RAW.spectra
       └─ SEEDS: asset_registry, rule_thresholds, bearing_catalog
       │
       ▼
    dbt Core (dbt-duckdb)
       │
       ├─ STAGING: stg_frames, stg_drive_telemetry, stg_spectra
       ├─ INTERMEDIATE: int_frames_enriched, int_rollup_1m, int_baselines, int_spectral_bands
       ├─ SNAPSHOTS: snap_device_position
       └─ MARTS: fct_exceedance_events, fct_asset_health_hourly, fct_plant_power_hourly,
                  dim_asset, fct_spectra_latest, fct_waterfall
       │
       ▼
    Streamlit app (Docker)
       │
       ├─ Page 1: Plant map (grid view, colors by status)
       ├─ Page 2: Asset detail (time series, ISO zones, temp/RH/dew)
       ├─ Page 3: Spectrum (latest, markers at 1x/2x/BPFO/BPFI)
       ├─ Page 4: Waterfall 3D (Plotly surface)
       ├─ Page 5: Events (timeline, classified)
       ├─ Page 6: Fleet (table, status, reasons, relube %, DQ coverage)
       ├─ Page 7: Power (PF trend, kW/kvar, target gaps)
       └─ Page 8: Evaluation (detection lead times vs truth)

Replay engine (optional):
  Generator → time-stepped data injection → DuckDB (live updates every 1s)
  → Streamlit auto-refresh → live demo effect

Services (Docker Compose):
  - duckdb: embedded, no separate server (DuckDB files + dbt)
  - streamlit: Flask-like app server on port 8501
```

**No Snowflake, no Terraform, no REST APIs, no roles/RBAC.** This is a local lab. Access control
not implemented (assume trusted environment).

---

## 3. Data contract

### 3.1 Overall frames — `vibration_frames_*.csv.gz`

One row per analysis frame per sensor. Frames arrive every **500 ms**; each frame summarizes a
dense raw burst computed on the device (noise from the surroundings already filtered).
Header must match exactly (legacy field names preserved in RAW):

| Column | Type | Unit | Notes |
|---|---|---|---|
| `timestamp` | string ISO-8601, 9 fractional digits, `Z` | UTC | e.g. `2026-09-16T12:00:00.123456789Z` |
| `device_ID` | string | — | sensor id, e.g. `VS-000123` |
| `X_amplitude` | float | µm peak-to-peak | **vertical** axis (most critical) |
| `X_frequency` | float | Hz | dominant frequency, no harmonics reported |
| `Y_amplitude` | float | µm peak-to-peak | **horizontal lateral** axis (second critical) |
| `Y_frequency` | float | Hz | |
| `Z_amplitude` | float | µm peak-to-peak | **axial** (along rotor); normally much lower than X/Y |
| `Z_frequency` | float | Hz | |
| `temperature` | float | °C | measured on the motor (bearing housing / frame) |
| `relative_humidity` | float | % | measured at the motor |
| `coordinates_position` | string, quoted | — | `"[floor,tandem,order]"`, e.g. `"[1,2,3]"` |

CSV rules: comma separated, header row, `"` enclosure (mandatory for `coordinates_position`),
gzip. Files partitioned by **arrival** hour: `frames/dt=YYYY-MM-DD/hh=HH/part-NNN.csv.gz`.

### 3.2 Drive telemetry — `drive_telemetry_*.csv.gz`

Motors run on variable frequency drives (VFD). Rotational speed is not measured by the sensor;
the drive feed is used to **confirm frequency** (1x) and to estimate load.

| Column | Type | Unit | Notes |
|---|---|---|---|
| `timestamp` | ISO-8601 ns `Z` | UTC | one row every 10 s |
| `drive_id` | string | — | e.g. `VFD-1-2-3` |
| `output_hz` | float | Hz | 0 when stopped |
| `voltage_l1l2_v`, `voltage_l2l3_v`, `voltage_l3l1_v` | float | V | line-to-line RMS, drive output |
| `current_l1_a`, `current_l2_a`, `current_l3_a` | float | A | RMS per phase |
| `phase_angle_l1_deg`, `phase_angle_l2_deg`, `phase_angle_l3_deg` | float | ° | voltage–current angle per phase |
| `power_factor` | float | — | total, as reported by the drive (see §13) |
| `run_state` | string | — | `RUN` / `STOP` / `FAULT` |

Note: with VFDs the reported power factor can be lower than `cos(phase_angle)` because of
harmonic distortion. Keep both; do not treat the difference as a data-quality error.

### 3.3 Spectrum snapshots — `spectra_*.ndjson.gz`

Periodic waveform captures processed into spectra (this is what feeds spectrum and waterfall
views). One JSON line per device × axis × snapshot:

```json
{"timestamp":"2026-09-16T12:00:00.000000000Z","device_ID":"VS-000123","axis":"X",
 "fs_hz":2560,"n_samples":2560,"window":"hann","df_hz":1.0,"f_max_hz":1000,
 "unit":"mm/s_rms","bins":[0.0012,0.0015, ...]}
```

Defaults: every **60 min** while running, 1 s capture at 2560 Hz → 1 Hz resolution, bins 0–1000 Hz
(1001 values), velocity RMS per bin. Configurable per profile.

### 3.4 Asset registry — `dbt/seeds/asset_registry.csv`

`device_ID, asset_id, asset_type (CONVEYOR_MOTOR|MILL_DRIVE), drive_id, plant_id, poles,
rated_kw, rated_current_a, iso_group (1|2), foundation (RIGID|FLEXIBLE), nominal_output_hz, bearing_de, bearing_nde,
relube_interval_h, installed_at`

Device ↔ position history comes from `coordinates_position` in the data, tracked with a dbt
snapshot (SCD2): a sensor moved or replaced keeps its history.

### 3.5 Bearing catalog — `dbt/seeds/bearing_catalog.csv`

`bearing_code, n_elements, element_d_mm, pitch_d_mm, contact_angle_deg`. Rows may be missing:
rules fall back to approximations (§4.4).

### 3.6 Truth labels — `truth/labels.csv` (evaluation only)

`label_id, asset_id, device_ID, scenario, start_ts, functional_failure_ts, end_ts, expected_reasons`

---

## 4. Physics and formulas

### 4.1 Displacement ↔ velocity ↔ acceleration (single dominant frequency)

With `d_pp` in µm and `f` in Hz (valid because the reported frequency has no harmonics):

- `d_peak_um = d_pp / 2`
- `v_rms_mm_s = 2π · f · d_peak_um · 1e-3 / √2  ≈ 2.2214e-3 · f · d_pp`
- `a_rms_mm_s2 = (2π · f)² · d_peak_um · 1e-3 / √2`

Sanity check: 50 µm pp at 25 Hz → ≈ 2.78 mm/s RMS.

Velocity RMS is the severity metric (ISO 20816-3 style). Displacement matters for slow machines
(≤ 600 rpm, e.g. mill rolls). Acceleration emphasizes high-frequency (bearing) content.

### 4.2 Running speed

- Synchronous speed: `f_sync_hz = output_hz · 2 / poles`
- Shaft speed (1x): `f_1x_hz = f_sync_hz · (1 − slip)`, default `slip = 0.02`
- Speed band: `band = floor(output_hz / band_width_hz)`, default `band_width_hz = 5`
  (baselines are per asset × speed band, because vibration changes with speed on VFDs)

Joining frames to drive telemetry: nearest previous drive row (`ASOF JOIN`), max staleness 30 s.

### 4.2b Load

- `v_avg = mean(voltage_l1l2, l2l3, l3l1)`, `i_avg = mean(current_l1, l2, l3)`
- `p_kw = √3 · v_avg · i_avg · power_factor / 1000`
- `load_pct = p_kw / rated_kw · 100`, `current_pct = max(current_lx) / rated_current_a · 100`

### 4.2c Phase unbalance (NEMA-style definition)

- `voltage_unbalance_pct = max(|V_lx − v_avg|) / v_avg · 100`
- `current_unbalance_pct = max(|I_lx − i_avg|) / i_avg · 100`
- Rule of thumb: a small voltage unbalance produces a current unbalance several times larger and
  extra winding heating roughly proportional to its square.
- Electrical vibration signature: twice the drive output frequency, `f_2lf = 2 · output_hz`.
  For a 4-pole motor this is far from 2x shaft (`2·f_1x ≈ output_hz`); for 2-pole motors they sit
  ~2·slip apart and need spectral resolution to separate.
- Load band: `floor(load_pct / 20)` (0–4). Baselines are per asset × speed band × load band.
- Frequency confirmation: `f_1x` derived from the drive vs dominant radial frequency when
  synchronous; persistent disagreement > 3 % while running → `SPEED_MISMATCH` (DQ flag).

### 4.3 Synchronous vs non-synchronous

`k = f_dominant / f_1x`. Synchronous if `|k − round(k)| ≤ 0.03` and `1 ≤ round(k) ≤ 4`.
Otherwise non-synchronous (bearing, electrical or structural candidates).

### 4.4 Bearing defect frequencies (per shaft speed `fr = f_1x`)

With geometry (`n`, `Bd`, `Pd`, `θ`):
- `FTF  = fr/2 · (1 − Bd/Pd·cosθ)`
- `BPFO = n/2 · fr · (1 − Bd/Pd·cosθ)`
- `BPFI = n/2 · fr · (1 + Bd/Pd·cosθ)`
- `BSF  = Pd/(2·Bd) · fr · (1 − (Bd/Pd·cosθ)²)`

Without geometry (rule of thumb): `FTF ≈ 0.4·fr`, `BPFO ≈ 0.4·n·fr`, `BPFI ≈ 0.6·n·fr`,
default `n = 8`. Match tolerance ±5 %, harmonics 1–3.

### 4.5 Dew point (Magnus)

`γ = ln(RH/100) + (17.62·T)/(243.12 + T)`, `T_dew = 243.12·γ / (17.62 − γ)`

### 4.6 Grease thermal aging (rule of thumb)

Grease life roughly halves for every 15 °C above 70 °C. Equivalent aging hours:
`h_eq = Σ Δt_h · 2^((T − 70)/15)` for `T > 70`, else `Δt_h`.
`relube_consumed_pct = h_eq_since_last_relube / relube_interval_h · 100`.

### 4.7 Forecast to threshold

Daily p95 velocity per asset × band, last 14 days, fit `ln(v) = a + b·t` (exponential growth is
typical of bearing degradation). Report `days_to_zone_c` only if ≥ 7 points and R² ≥ 0.6.

---

## 5. Generator

### 5.1 Profiles

| Profile | Assets | Days | Frame rate | Spectra | Purpose |
|---|---|---|---|---|---|
| `dev` | 12 | 21 | 1 frame / 10 s | every 60 min | fast iteration, cheap |
| `demo` | 24 | 30 | 1 frame / 2 s | every 60 min | dashboard showcase |
| `full` | 24 | 3 | 2 frames / s | every 10 min | realism at native rate |

Deterministic by `--seed`. Scenario timelines scale to the profile duration.

### 5.2 Plant model

`PLANT-A`, floors 1–2, tandems 1–3, order 1–4. Conveyor motors (group 2, rigid, 4 poles, 60 Hz
nominal) plus a few mill drives (group 1, rigid, slower). Ambient: daily cycle 24–32 °C, RH 60–95 %
inversely correlated. Operating profile: shifts with stops; VFD setpoint changes every 30–120 min
within 35–60 Hz; occasional full stops overnight.

### 5.3 Signal model

Each axis is a sum of components `(f_i, v_rms_i)`; frame values derived as:
- component displacement `d_pp_i = v_rms_i · 450.16 / f_i` (inverse of §4.1)
- `X|Y|Z_amplitude = sqrt(Σ d_pp_i²)` + noise
- `X|Y|Z_frequency = f` of the component with max `d_pp_i`, ±0.5 % jitter

Healthy baseline: 1x residual unbalance, velocity 0.6–1.2 mm/s at nominal speed, scaling with speed;
axis factors X 1.0, Y 0.85, Z 0.3. Drive: current ∝ load with PF 0.80–0.88 at nominal load, lower at light load; mechanical faults add 2–8 % current (friction/misalignment). Temperature: ambient + load rise (∝ load_pct²) with
first-order lag τ = 30 min. Spectra are synthesized from the same components plus a broadband
noise floor, windowed (Hann) and FFT-ed with numpy — never from the frame stream.

Note on realism: in displacement, low frequencies dominate. A bearing tone becomes the reported
dominant frequency only late in degradation. Early bearing evidence appears in spectra
(acceleration/velocity bins), not in frames. The generator must preserve this.

### 5.4 Fault scenarios (each writes truth labels)

| Scenario | Signature |
|---|---|
| `UNBALANCE_GROWTH` | 1x radial (X, Y) grows ×3 over the period; Z stays low |
| `MISALIGNMENT_AFTER_MAINT` | step change after a maintenance stop: Z rises to ≥ 0.6·max(X,Y), 2x appears |
| `LOOSENESS` | X ≫ Y (X/Y ≥ 2), intermittent recurrent spikes, dominant alternates 1x/2x |
| `BEARING_OUTER_RACE` | BPFO + harmonics rise exponentially in spectra; late: becomes dominant non-sync in frames, noise floor rises, temperature rises |
| `LUBRICATION_LOSS` | temperature ramps +20 °C over ~12 h at stable speed, mild bearing-band rise; relube event resets |
| `PHASE_UNBALANCE` | voltage unbalance ramps to ~3 %, current unbalance ~15–20 %, temperature rise, energy at `2·output_hz` in spectra |
| `SINGLE_PHASING` | short event: one phase current → ~0 while running, others jump; temperature spike; drive trips to `FAULT` |
| `RESONANCE_BAND` | not a fault: vibration ×2.5 only while output_hz in 44–48 Hz |
| `CONDENSATION` | motor stopped overnight, RH ≥ 90 %, temperature near dew point |

Most assets stay healthy (control group).

### 5.5 Data-quality injections

Duplicates (0.2 %, identical rows), out-of-order within 2 s, stuck sensor (identical values
≥ 2 min), dropout (gap 5–30 min), late files (arrive up to 6 h after event time), one sensor
relocation (new `coordinates_position`) and one sensor replacement (new `device_ID`, same asset).

### 5.6 Generator tests (minimum)

Formula round-trip (§4.1) within 0.1 %; FFT of a synthetic sine recovers frequency ±1 bin and
amplitude ±2 %; CSV header exact match; determinism (same seed → same hash); every scenario has a
truth label; profile row counts within ±1 % of expected.

---

## 6. DuckDB foundation and ingest

**No Terraform.** DuckDB is embedded; `.duckdb` file lives in repo root (git-ignored).

**Setup (one-time):**
```bash
python ingest/setup.py  # creates .duckdb, schemas RAW/STAGING/MARTS/EVAL
```

**Schemas created:**
- `RAW` — raw data tables (vibration_frames, drive_telemetry, spectra)
- `STAGING` — dbt staging layer
- `INTERMEDIATE` — dbt intermediate layer
- `MARTS` — dbt mart layer (for dashboards)
- `EVAL` — dbt evaluation layer (vs truth labels)
- `SEEDS` — static data (asset_registry, rule_thresholds, bearing_catalog)

**Data ingestion (Python script):**
```bash
python ingest/load.py [--profile dev|demo|full]
# Reads CSV/NDJSON from data/ (generated by make gen)
# Loads into RAW schema
# Idempotent: re-running skips duplicates (checked by _file_name + _file_row)
```

**CSV format (DuckDB):**
- Header row, comma-separated, `"` field enclosure (for `coordinates_position`)
- gzip compression
- Timestamps: ISO-8601 with 9 fractional digits and `Z` suffix
- DuckDB auto-detects schema; seed types in `dbt/seeds/` CSVs

**Metadata columns added by loader:**
- `_file_name` (source file path)
- `_file_row` (row number in source)
- `_loaded_at` (timestamp when inserted)

---

## 7. dbt models

**staging**
- `stg_frames`: rename to snake_case with units, cast ts to `TIMESTAMP_NS` (nanoseconds), parse
  coordinates to `floor`, `tandem`, `order_pos`; dedup with `qualify row_number() over (partition by device_id, timestamp order by _loaded_at) = 1`.
- `stg_drive_telemetry`, `stg_spectra` (bins kept as ARRAY or LIST in DuckDB).

**snapshots**
- `snap_device_position`: SCD2 of device → coordinates.

**intermediate**
- `int_frames_enriched` (incremental, lookback 6 h for late data): ASOF JOIN drive telemetry,
  `f_1x_hz`, `p_kw`, `load_pct`, speed band, load band, per-axis `v_rms_mm_s`, `a_rms_mm_s2`, `k` ratio, sync flag, dew point,
  DQ flags (stuck, gap, stale drive data).
- `int_rollup_1m`: per device × minute: p50/p95/max velocity per axis, temp mean/max, RH mean,
  non-sync fraction, dominant freq mode, running flag, DQ coverage.
- `int_baselines`: per asset × speed band × load band from the commissioning window (first 3 days of healthy
  running per asset, or `installed_at` + 3 days): p50/p95 per axis and temperature.
- `int_spectral_bands`: per snapshot: energy in bands around 1x, 2x, BPFO, BPFI (and harmonics),
  broadband noise floor (median of bins).

**marts**
- `fct_exceedance_events`: gaps-and-islands over thresholds, classified (§8.3).
- `fct_asset_health_hourly`: status, reason codes, `days_to_zone_c`, `relube_consumed_pct`,
  `rules_version`.
- `fct_plant_power_hourly`: per plant × hour: total `p_kw`, estimated `q_kvar = p_kw · tan(acos(pf))`
  per drive summed, power-weighted PF, kvar needed to reach a target PF (seed, default 0.95).
- `dim_asset`, `fct_spectra_latest`, `fct_waterfall` (last N snapshots per device × axis).

**eval**
- `eval_detection`: per truth label: first detection time, lead time before
  `functional_failure_ts`, matched reasons; per healthy asset: false alert count.

Tests: `unique`/`not_null` on keys, `relationships` to registry, accepted values for status and
reason codes, source freshness on RAW, custom test: every truth scenario detected with lead
time > 0 (`eval`), false alerts on control assets ≤ configured budget.

---

## 8. Health rules

All values below are **defaults** stored in `rule_thresholds.csv`
(`rule_id, parameter, value, unit, applies_to, version, effective_from, rationale`).
They are starting points, not normative values; confirm ISO boundaries against the standard.

### 8.1 Vibration severity (velocity RMS, per axis, 1-min p95)

| Group / foundation | A/B | B/C (ALERT) | C/D (DANGER) |
|---|---|---|---|
| Group 2, rigid | 1.4 | 2.8 | 4.5 |
| Group 2, flexible | 2.3 | 4.5 | 7.1 |
| Group 1, rigid | 2.3 | 4.5 | 7.1 |
| Group 1, flexible | 3.5 | 7.1 | 11.0 |

WATCH when above A/B persistently. Relative rules (per asset × speed band baseline), evaluated
only when absolute value > A/B × 0.5 (avoid alarms on tiny numbers):
- WATCH: p95 > 2.0 × baseline p95 for ≥ 10 of last 15 min
- ALERT: p95 > 3.0 × baseline p95 for ≥ 10 of last 15 min

### 8.2 Diagnostic ratios (reason codes, persistent ≥ 30 min)

- `AXIAL_HIGH` (misalignment suspect): Z ≥ 0.5 · max(X, Y) and Z above A/B × 0.5
- `VERTICAL_DOMINANT` (looseness / soft foot suspect): X / Y ≥ 2.0
- `SYNC_2X` : dominant k ≈ 2 on Z or radial for ≥ 30 % of frames in window

### 8.3 Event classification (how peaks are judged)

Threshold crossings are compared with the previous values and tracked over time:
- `TRANSIENT`: island < 30 s and ≤ 2 islands in 60 min → logged, no status change
- `RECURRENT`: ≥ 3 islands in 60 min → WATCH
- `PERSISTENT`: island ≥ 5 min → escalates to the level of the threshold crossed
- `STEP_CHANGE`: 1-min p95 > 1.5 × median of previous 60 min and holds ≥ 10 min
- `RESONANCE_SUSPECT`: exceedances confined to one speed band on ≥ 3 separate occasions while other
  bands stay normal → flagged for engineering, **does not** raise fault status

### 8.4 Bearing rules

- `BEARING_EARLY` → WATCH: in spectra, BPFO or BPFI band energy > 3 × baseline in ≥ 2 of last
  3 snapshots
- `BEARING_DEVELOPED` → ALERT: band energy > 6 × baseline, or harmonics present, or in frames
  non-sync fraction ≥ 20 % for 6 h
- `BEARING_LATE` → DANGER: noise floor > 3 × baseline **and** (velocity above B/C or temperature rule)
- Temperature confirmation: any bearing rule + a temperature rule below → escalate one level
  (temperature is a late indicator; temperature alone → check lubrication, load, cooling)

### 8.5 Temperature rules (bearing housing / frame)

- Absolute: WATCH 80 °C, ALERT 90 °C, DANGER 100 °C (per-asset override allowed)
- Peer: motor vs median of running peers in same floor + tandem and same speed band:
  WATCH > +10 °C, ALERT > +15 °C, persistent 30 min
- Own baseline (same speed band): WATCH > +10 °C, ALERT > +15 °C, persistent 30 min
- Rate: > 5 °C in 30 min with speed change < 5 % → ALERT (`TEMP_RATE`, lubrication loss / overload)
- Grease: `relube_consumed_pct` ≥ 90 → `RELUBE_DUE` (maintenance flag, not a fault status)

### 8.5b Electrical / load rules

- `OVERLOAD`: `current_pct` > 100 for ≥ 10 min → ALERT; > 115 for ≥ 2 min → DANGER
- `CURRENT_DRIFT`: current > own baseline (same speed × load band) + 8 % for ≥ 2 h at stable speed →
  WATCH (mechanical drag: bearing friction, misalignment, lubrication)
- `VOLTAGE_UNBALANCE`: > 1 % for ≥ 15 min → WATCH; > 2 % → ALERT; > 5 % → DANGER
- `CURRENT_UNBALANCE`: > 10 % for ≥ 15 min → WATCH; > 15 % → ALERT (evaluate only at load_pct ≥ 30,
  unbalance percentages inflate at light load)
- `SINGLE_PHASING`: any phase current < 10 % of `i_avg` while `RUN` → DANGER immediately
- `ELECTRICAL_2LF`: spectral energy at `2·output_hz` > 3 × baseline together with voltage or
  current unbalance → escalates the unbalance rule one level
- `PF_DROP`: power factor < baseline − 0.08 at comparable load for ≥ 1 h → WATCH (info for electrical team)
- Temperature rules in §8.5 compare against baselines of the same load band, so a hot motor under
  heavy load is not flagged as a bearing problem.

### 8.6 Environment and operation

- `CONDENSATION_RISK`: stopped ≥ 30 min, RH ≥ 85 %, `temperature − T_dew ≤ 3 °C` (info)
- `LOW_SPEED_OPERATION`: output_hz < 30 % nominal for ≥ 4 h (info: thin lubrication film)

### 8.7 Forecast

`days_to_zone_c < 14` → ALERT (`TREND_TO_ZONE_C`), `< 30` → WATCH.

### 8.8 Status aggregation

Levels: `UNKNOWN < NORMAL < WATCH < ALERT < DANGER`. Status = worst active rule.
`UNKNOWN` when DQ coverage in the hour < 80 % or drive data stale — never report NORMAL on bad data.
Hysteresis: de-escalate only after 60 min below the lower threshold × 0.9. Every row carries
`reason_codes ARRAY` and `rules_version`.

---

## 9. Evaluation

`eval_detection` must show, per scenario: detected (yes/no), first reason code, lead time before
functional failure; per control asset: false WATCH/ALERT counts. Targets for v1: all fault
scenarios detected with positive lead time; `RESONANCE_BAND` never raises fault status;
≤ 1 false ALERT per control asset per 30 days.

---

## 10. Streamlit app (open source, Docker)

**Runs:** `streamlit run app/streamlit_app.py` in Docker container on port 8501. Reads only MARTS
schema. Cached queries via `@st.cache_data`; never query frames older than selected window at raw
granularity (use `int_rollup_1m` beyond 6 h).

**Architecture:**
- `app/streamlit_app.py` — main app, navigation
- `app/pages/` — page modules (one file per page)
- `app/queries/` — DuckDB connection helpers and cached SQL queries
- `requirements.txt` — Streamlit, Plotly, Altair, duckdb, pandas, numpy

**Pages:**
1. **Plant map** — grid per floor: tandems × order, colored by status, tooltip with reasons.
2. **Asset detail** — three time-series charts (X, Y, Z velocity; toggle µm pp), ISO zone bands as
   shaded areas, event markers; temperature + RH + dew point; drive speed.
3. **Spectrum** — latest snapshot per axis with markers at 1x, 2x, BPFO, BPFI (± tolerance).
4. **Waterfall 3D** — Plotly surface: time × frequency × amplitude, last N snapshots, axis selector.
5. **Events** — timeline of classified events with filters.
6. **Fleet** — table: status, reasons, days_to_zone_c, relube %, DQ coverage, rules_version.
7. **Power** — plant PF trend, kW/kvar, kvar gap to target PF (supports capacitor bank or
   synchronous condenser decisions). Note in the page: the drive-reported PF is not the utility
   meter PF; harmonics from VFDs matter when sizing capacitors (detuned banks).
8. **Evaluation** — detection lead times vs truth (clearly labeled as lab-only).

**Look & feel:** Clean, own identity. No vendor-copied styling. Educational focus: formulas visible,
units clear, assumptions documented inline.

---

## 11. Deployment (Docker Compose)

**No REST APIs.** Local orchestration via `docker-compose.yml`:

```yaml
services:
  duckdb:
    # Implicit: DuckDB is embedded in dbt container, not a separate service
    # .duckdb file mounted as volume, persistent across restarts
  
  streamlit:
    build: ./app
    ports:
      - "8501:8501"
    volumes:
      - .:/app/workspace
    environment:
      - DUCKDB_PATH=/app/workspace/.duckdb
    command: streamlit run streamlit_app.py
```

**Deployment:**
```bash
make docker-build          # build Streamlit image
make docker-up             # start containers
docker-compose logs -f     # watch logs
make docker-down           # stop
```

**Smoke test:** After `docker-compose up`, app is live at `http://localhost:8501`. Page load
should succeed in < 3 s. Check **Fleet** page loads without errors.

**Rollback:** `git checkout <commit>`, rebuild, restart.

**Alerts:** Not implemented (v1). Can add via dbt tests + email hook post-v1.

---

## 12. CI / CD

**GitHub Actions (on every PR):**
- Lint: `ruff check generator/ dbt/ app/`
- Test: `pytest generator/tests/` (generator tests, formulas, FFT, determinism)
- dbt test: `dbt test -s +fct_asset_health_hourly` (including eval tests vs truth labels)
- Build: `docker build ./app` (check Streamlit app builds)

**On merge to main:**
- Build + push Docker image (optional: to Docker Hub or ghcr.io)
- Create release tag
- Update README with latest version

**No zero-copy clones.** DuckDB is fast; full `dbt build` on every PR is acceptable.

---

## 13. Data replay engine (live dashboard demos)

**Purpose:** Inject synthetic data into DuckDB with controlled timesteps to simulate "live" motor
data. Enables demos where the Streamlit dashboard auto-refreshes as new "measurements" arrive
every 1 second.

**How it works:**
1. Generator produces data with realistic timestamps (e.g., 2026-09-16 12:00:00 to 12:30:00).
2. Replay script reads generated CSV/NDJSON files.
3. Injects data into RAW tables with a **delay function**: row with timestamp T is inserted at
   wall-clock time T (or compressed: T/compression_factor).
4. dbt runs on a schedule (every 1 min, or triggered by ingest).
5. Streamlit auto-refreshes (st.cache_data + st.rerun with interval).

**Implementation:**
```python
# replay/replay.py
import time, gzip, csv, duckdb, sys
from datetime import datetime, timedelta

def replay(profile, compression_factor=1.0):
    """
    profile: 'dev' | 'demo' | 'full'
    compression_factor: 60 means 1 hour of data replays in 1 minute
    """
    db = duckdb.connect('.duckdb')
    gen_data_dir = f'data/{profile}'
    
    # Read frames, sorted by timestamp
    frames_file = glob.glob(f'{gen_data_dir}/frames/**/*.csv.gz')[0]
    with gzip.open(frames_file) as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    
    start_time = parse_timestamp(rows[0]['timestamp'])
    wall_clock_start = datetime.utcnow()
    
    for row in rows:
        row_time = parse_timestamp(row['timestamp'])
        delay_sec = (row_time - start_time).total_seconds() / compression_factor
        
        wall_clock_now = datetime.utcnow()
        elapsed = (wall_clock_now - wall_clock_start).total_seconds()
        if elapsed < delay_sec:
            time.sleep(delay_sec - elapsed)
        
        # Insert row into RAW.vibration_frames
        db.execute(f"INSERT INTO RAW.vibration_frames VALUES (...)")
        print(f"[{datetime.utcnow()}] Inserted frame ts={row_time}")
```

**Usage:**
```bash
# Demo: 30 min of data replays in 30 seconds (60x compression)
make replay PROFILE=dev COMPRESSION=60

# In parallel, Streamlit app is running:
docker-compose up streamlit
```

**Streamlit refresh:** Pages use `@st.cache_data(ttl=5)` (5 sec cache). With replay sending data
every second, the dashboard feels "live."

---

## 14. Assumptions to confirm

1. **Physics:** Drive feed structure (frequency, voltage, current, phase angle, PF) and vibration
   amplitudes (peak-to-peak µm) are as specified in §3.
2. **Temperature/RH:** Measured on motor housing/frame at the sensor location.
3. **Excluded parameters (v1):** The six IMU parameters (orientation angles, angular velocity)
   are out of scope; schema can add them post-v1 as nullable columns.
4. **Default motor:** 4 poles, 60 Hz nominal, 2 % slip.
5. **Waveform snapshots:** Exist and are distinct from frame stream. Frames feed time-series
   dashboards; spectra feed waterfall and spectral pages.
6. **Streamlit + Plotly:** Docker image can install Plotly + Altair from PyPI (no special
   Snowflake Anaconda channel needed).
7. **DuckDB performance:** Sufficient for analytics queries on 21-30 days of data, 12-24 assets,
   500 ms sampling (frame data will be ~10-100 MB; spectra ~50 MB). If slow, add columnar
   compression (dbt + DuckDB parquet export).

---

## 15. Phases

| # | Phase | Deliverable |
|---|---|---|
| 0 | Scaffold | repo layout, Makefile, tooling, Docker Compose, CI lint |
| 1 | Generator: frames + drive + truth + DQ | `make gen PROFILE=dev`, tests §5.6 |
| 2 | Generator: spectra | NDJSON spectra, FFT tests §5.6 |
| 3 | DuckDB setup + ingest | `python ingest/setup.py`, `python ingest/load.py`, load checks |
| 4 | dbt staging + snapshot + intermediate | models + tests, dbt build on DuckDB |
| 5 | dbt health rules + seeds + marts | §8 implemented, `rules_version` tracking |
| 6 | dbt eval | §9 targets as tests (detection lead times) |
| 7 | Streamlit app | pages §10 (plant map, asset detail, spectrum, waterfall, events, fleet, power, eval) |
| 8 | Data replay engine | `make replay`, time-stepped injection, live demo effect |
| 9 | Docker Compose + CI + README | docker-compose.yml, GitHub Actions (lint/test/build), README.md in English |
