

-- 1-minute rollups: p50, p95, max velocity per axis + temp, RH, running flag
with enriched as (
  select * from "motor_health_lab"."raw_intermediate"."int_frames_enriched"
),

rollup as (
  select
    date_trunc('minute', timestamp_ns) as minute_start_ns,
    device_id,
    floor,
    tandem,
    order_pos,
    -- Velocity percentiles per axis
    approx_quantile(x_v_rms_mm_s, 0.50) as x_v_rms_p50_mm_s,
    approx_quantile(x_v_rms_mm_s, 0.95) as x_v_rms_p95_mm_s,
    max(x_v_rms_mm_s) as x_v_rms_max_mm_s,
    approx_quantile(y_v_rms_mm_s, 0.50) as y_v_rms_p50_mm_s,
    approx_quantile(y_v_rms_mm_s, 0.95) as y_v_rms_p95_mm_s,
    max(y_v_rms_mm_s) as y_v_rms_max_mm_s,
    approx_quantile(z_v_rms_mm_s, 0.50) as z_v_rms_p50_mm_s,
    approx_quantile(z_v_rms_mm_s, 0.95) as z_v_rms_p95_mm_s,
    max(z_v_rms_mm_s) as z_v_rms_max_mm_s,
    -- Temperature
    avg(temperature_c) as temperature_mean_c,
    max(temperature_c) as temperature_max_c,
    -- Humidity
    avg(relative_humidity_pct) as relative_humidity_mean_pct,
    -- Running state
    case when max(case when run_state = 'RUN' then 1 else 0 end) = 1 then true else false end as is_running,
    -- Non-sync fraction
    count(case when x_k is not null and abs(x_k - round(x_k)) > 0.03 then 1 end)::double /
      nullif(count(*), 0) as non_sync_fraction,
    -- Count for data quality
    count(*) as frame_count
  from enriched
  group by 1, 2, 3, 4, 5
)

select * from rollup