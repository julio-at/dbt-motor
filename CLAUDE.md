# CLAUDE.md — motor-health-lab

**Educational learning lab** for condition monitoring of industrial motors (conveyors, mill drives).
Built entirely **local** with **DuckDB** + **Docker Compose**: synthetic sensor data → dbt → health
rules → **Streamlit** dashboard. Reproducible, controlled, free. Source truth for building real
condition monitoring systems.

The technical contract lives in `docs/SPEC.md`. Read relevant sections before each phase.

## Golden rules (non-negotiable)

1. **KISS.** No Snowflake, no Airflow, no Kafka, no Kubernetes, no external services.
   Everything runs in Docker Compose locally. Anything not in `docs/SPEC.md` must be proposed
   and approved first.

2. **One phase at a time.** Work only on the requested phase. Start in plan mode, show the plan,
   await approval, then implement. Commit at end of each phase (Conventional Commits).

3. **Tests or it didn't happen.** Every phase ships with tests. Run them before declaring done,
   report exact commands and results.

4. **No real names.** Never reference real companies, clients, plants, products. Plants: `PLANT-A`,
   assets: `CNV-…` / `MILL-…`. Synthetic data only. This is a learning tool, not a prod system.

5. **No secrets in repo.** Config via `.env` (commit `.env.example` only). All credentials/keys
   in container env vars, never in code.

6. **Honest physics.** Use formulas in `docs/SPEC.md` §4. Never FFT the frame stream; spectra
   come only from waveform snapshots (§3.3). Validate against real bearing/mechanical theory.

7. **No magic numbers in code.** Thresholds live in `dbt/seeds/rule_thresholds.csv`. Every health
   row records `rules_version` that produced it. Traceability matters.

8. **Time, not frames.** Window/persistence rules in seconds/minutes, never frame counts.

9. **Truth labels for eval only.** Feed `eval_*` models and tests, never touch detection logic.

10. **Units in column names:** `_um_pp`, `_hz`, `_mm_s`, `_mm_s2`, `_c`, `_pct`, `_rpm`.

11. **Before touching code:** Verify SPEC against DuckDB docs. If something can't run locally,
    that's a blocker — record in `docs/decisions.md`.

12. **Direct implementation.** No subagent delegation. You (Claude) own every line. Julio reviews
    diffs, approves/requests changes, then you commit. Full accountability.

## Language & style

- Code, comments, docs, commits: **English**.
- Python **3.11** everywhere. Type hints, `ruff` linting, `pytest` testing.
- SQL: lowercase keywords, CTE-first, one model per file, DuckDB-compatible syntax.
- Timestamps UTC, nanosecond precision (`TIMESTAMP_NTZ(9)` → DuckDB `TIMESTAMP_NS`).

## Dev environment

- Primary: **macOS** (zsh, Homebrew); CI on **Ubuntu** (GitHub Actions).
- macOS BSD tools: avoid GNU-only flags (`sed -i` without suffix, `date -d`), use Python instead.
- Python 3.11 via Homebrew/uv; no system Python mods.
- Docker Desktop required (for `docker compose`).
- Ignore: `.DS_Store`, `.env` (not `.env.example`), `data/` (generated), `.duckdb` files.

## Stack (approved, no changes)

| Layer | Choice |
|---|---|
| Generator | Python 3.11, numpy, deterministic seed-based |
| Database | DuckDB (local, embedded, zero-config) |
| Ingest | Python script: CSV/NDJSON → DuckDB load |
| Transform | dbt Core + dbt-duckdb adapter |
| Dashboard | Streamlit (open source) in Docker |
| Replay engine | Python script: time-stepped data injection for live demo (1s refresh) |
| CI | GitHub Actions; pytest for generator/dbt tests |

## Layout

```
generator/           synthetic data generator (frames, drive, spectra, truth labels)
generator/profiles/  dev/demo/full profile configs
ingest/              data loading scripts (CSV → DuckDB)
dbt/                 models/{staging,intermediate,marts,eval}, seeds, snapshots, macros, tests
app/                 Streamlit app (streamlit_app.py, pages/, requirements.txt)
replay/              time-stepped data replay engine (for live dashboards)
docker-compose.yml   services: duckdb (embedded), streamlit
docs/                SPEC.md, decisions.md, setup guide
.github/workflows/   lint, test, build
Makefile
```

## Commands (keep updated)

```
make gen PROFILE=dev               # synthetic data into data/ (gitignored)
make test                          # pytest: generator + dbt tests
make dbt-build                     # dbt build on DuckDB
make docker-build                  # build Streamlit Docker image
make docker-up                     # docker-compose up (DuckDB + Streamlit)
make docker-down                   # stop services
make app-test                      # smoke test app pages
make replay PROFILE=dev            # live data replay (timesteps, 1s refresh)
```

## Cost guardrails

**FREE.** DuckDB is embedded, no cloud spend. Docker runs locally. Data lives in `.duckdb` files
(gitignored). Generator profile default is `dev` (small, fast). Replay is controllable (timestep
granularity).

## Working agreement with Julio

- **You (Claude) own the implementation.** Write every line. Julio reviews diffs, approves phase
  by phase. No external subagents.
- **Plan first.** Before writing code, propose architecture in CLAUDE.md-compliant plan. Wait
  for "listo" before coding.
- **Commit often.** Each phase is one commit (or logical sub-commits within phase if complex).
  Use conventional commit format.
- **README is law.** By end, README.md in English must be complete enough that anyone can
  `git clone && docker-compose up && make replay` and see it working.
- **Learning focus.** This is educational. Code must be clear, formulas documented, physics
  verifiable. Not a black box.
