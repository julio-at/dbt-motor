{{
  config(
    materialized='table',
    schema='marts',
  )
}}

-- Asset health status per hour: implements SPEC §8 health rules
with hourly_data as (
  select
    date_trunc('hour', minute_start_ns) as hour_start_ns,
    device_id,
    floor,
    tandem,
    order_pos,
    -- Velocity metrics (SPEC §8.1)
    max(x_v_rms_p95_mm_s) as x_v_rms_p95_mm_s,
    max(y_v_rms_p95_mm_s) as y_v_rms_p95_mm_s,
    max(z_v_rms_p95_mm_s) as z_v_rms_p95_mm_s,
    avg(temperature_mean_c) as temperature_mean_c,
    max(temperature_max_c) as temperature_max_c,
    avg(relative_humidity_mean_pct) as relative_humidity_mean_pct,
    count(case when is_running then 1 end)::double / count(*) as running_fraction
  from {{ ref('int_rollup_1m') }}
  group by 1, 2, 3, 4, 5
),

-- Join with asset specs and thresholds
with_thresholds as (
  select
    h.*,
    a.iso_group,
    a.foundation,
    a.rated_kw,
    a.rated_current_a,
    t_ab.value as vibe_ab_threshold,
    t_bc.value as vibe_bc_threshold,
    t_cd.value as vibe_cd_threshold,
    t_temp_watch.value as temp_watch_threshold,
    t_temp_alert.value as temp_alert_threshold,
    t_temp_danger.value as temp_danger_threshold
  from hourly_data h
  left join {{ ref('asset_registry') }} a on h.device_id = a.device_id
  left join {{ ref('rule_thresholds') }} t_ab
    on a.iso_group = 2 and a.foundation = 'RIGID' and t_ab.rule_id = 'VIBE_G2_RIGID_AB'
  left join {{ ref('rule_thresholds') }} t_bc
    on a.iso_group = 2 and a.foundation = 'RIGID' and t_bc.rule_id = 'VIBE_G2_RIGID_BC'
  left join {{ ref('rule_thresholds') }} t_cd
    on a.iso_group = 2 and a.foundation = 'RIGID' and t_cd.rule_id = 'VIBE_G2_RIGID_CD'
  left join {{ ref('rule_thresholds') }} t_temp_watch
    on t_temp_watch.rule_id = 'TEMP_ABSOLUTE_WATCH'
  left join {{ ref('rule_thresholds') }} t_temp_alert
    on t_temp_alert.rule_id = 'TEMP_ABSOLUTE_ALERT'
  left join {{ ref('rule_thresholds') }} t_temp_danger
    on t_temp_danger.rule_id = 'TEMP_ABSOLUTE_DANGER'
),

-- Evaluate rules (SPEC §8)
rules_evaluated as (
  select
    hour_start_ns,
    device_id,
    floor,
    tandem,
    order_pos,
    iso_group,
    foundation,
    x_v_rms_p95_mm_s,
    y_v_rms_p95_mm_s,
    z_v_rms_p95_mm_s,
    temperature_mean_c,
    temperature_max_c,
    running_fraction,
    -- Vibration severity (SPEC §8.1)
    case
      when greatest(x_v_rms_p95_mm_s, y_v_rms_p95_mm_s) >= vibe_cd_threshold then 'DANGER'
      when greatest(x_v_rms_p95_mm_s, y_v_rms_p95_mm_s) >= vibe_bc_threshold then 'ALERT'
      when greatest(x_v_rms_p95_mm_s, y_v_rms_p95_mm_s) >= vibe_ab_threshold then 'WATCH'
      else 'NORMAL'
    end as vibration_status,
    -- Temperature (SPEC §8.5)
    case
      when temperature_max_c >= temp_danger_threshold then 'DANGER'
      when temperature_max_c >= temp_alert_threshold then 'ALERT'
      when temperature_max_c >= temp_watch_threshold then 'WATCH'
      else 'NORMAL'
    end as temperature_status,
    -- Overall status: worst of all rules
    greatest(
      case when greatest(x_v_rms_p95_mm_s, y_v_rms_p95_mm_s) >= vibe_cd_threshold then 4
           when greatest(x_v_rms_p95_mm_s, y_v_rms_p95_mm_s) >= vibe_bc_threshold then 3
           when greatest(x_v_rms_p95_mm_s, y_v_rms_p95_mm_s) >= vibe_ab_threshold then 2
           else 1 end,
      case when temperature_max_c >= temp_danger_threshold then 4
           when temperature_max_c >= temp_alert_threshold then 3
           when temperature_max_c >= temp_watch_threshold then 2
           else 1 end
    ) as status_code
  from with_thresholds
),

-- Assign status names
final as (
  select
    hour_start_ns,
    device_id,
    floor,
    tandem,
    order_pos,
    iso_group,
    foundation,
    x_v_rms_p95_mm_s,
    y_v_rms_p95_mm_s,
    z_v_rms_p95_mm_s,
    temperature_mean_c,
    temperature_max_c,
    running_fraction,
    vibration_status,
    temperature_status,
    case status_code
      when 4 then 'DANGER'
      when 3 then 'ALERT'
      when 2 then 'WATCH'
      else 'NORMAL'
    end as overall_status,
    concat_ws(',', vibration_status, temperature_status) as reason_codes,
    '1.0' as rules_version
  from rules_evaluated
)

select * from final
