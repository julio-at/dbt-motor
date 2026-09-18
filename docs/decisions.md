# Architectural Decisions — motor-health-lab

## 1. DuckDB over Snowflake

**Decision:** Use embedded DuckDB for local analytics instead of Snowflake cloud.

**Rationale:**
- Zero cost (no cloud spend)
- Full control (data, compute, schema)
- Fast iteration (no queuing, instant results)
- Educational focus (learn analytics patterns without enterprise complexity)
- Reproducible (anyone can clone + run locally)

**Trade-offs:**
- No multi-tenancy, no RBAC (acceptable for learning lab)
- Single-machine performance (sufficient for 21-30 days of synthetic data)
- No built-in HA (not needed for demo/learning)

## 2. Docker Compose over Kubernetes

**Decision:** Orchestrate with docker-compose locally, not Kubernetes.

**Rationale:**
- KISS principle (no cluster, no overhead)
- Everyone has Docker Desktop (macOS, Ubuntu, Windows)
- Fast startup (seconds, not minutes)
- Easy to modify (docker-compose.yml is readable YAML)

**Trade-offs:**
- Single host (no multi-node)
- Suitable for demos/labs, not production
- Learning value is still high (Docker concepts apply everywhere)

## 3. Streamlit open source (not in Snowflake)

**Decision:** Use Streamlit open source in Docker, not Streamlit in Snowflake.

**Rationale:**
- Flexibility (install any Python library)
- Portable (same app runs locally, in cloud, or Hugging Face)
- Learning value (understand Streamlit as a framework, not a Snowflake product)
- Cost (free)

**Trade-offs:**
- No Snowflake zero-trust (data doesn't stay in warehouse)
- Manage secrets explicitly (.env file)
- Acceptable for synthetic data lab

## 4. Replay engine for live demos

**Decision:** Add time-stepped data injection (Phase 8) to simulate "live" arrivals.

**Rationale:**
- Makes dashboards feel real (auto-refresh as new data arrives)
- Educational (shows how streaming patterns work)
- Low overhead (Python script, not Kafka/Pub-Sub)
- Controllable (compression factor for demos)

**Trade-offs:**
- Adds complexity (Phase 8)
- Only works for pre-generated data (not true real-time)
- Acceptable for learning/demo

## 5. dbt with DuckDB adapter

**Decision:** Use dbt-core + dbt-duckdb instead of dbt-snowflake.

**Rationale:**
- dbt patterns are the same (models, tests, snapshots, macros)
- Learning transfer (same SQL skills on any warehouse)
- Fast (DuckDB is OLAP-optimized)
- Cost (no Snowflake adapter costs)

**Trade-offs:**
- DuckDB SQL dialect is slightly different (usually compatible)
- Less mature than dbt-snowflake (acceptable for learning)

---

**Status:** Phase 0 complete (scaffold). Decisions may evolve as phases progress.
