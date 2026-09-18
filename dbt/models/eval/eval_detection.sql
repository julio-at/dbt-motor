{{
  config(
    materialized='table',
    schema='eval',
  )
}}

-- Evaluate detection: compare health rules vs truth labels
with truth as (
  select * from {{ source('raw', 'truth_labels') }}
),

health_hourly as (
  select * from {{ ref('fct_asset_health_hourly') }}
),

-- For each truth label, find first detection time
detections as (
  select
    t.label_id,
    t.asset_id,
    t.scenario,
    t.start_ts::timestamp_ns as start_ts,
    t.functional_failure_ts::timestamp_ns as failure_ts,
    t.end_ts::timestamp_ns as end_ts,
    min(case
      when h.hour_start_ns >= t.start_ts::timestamp_ns
        and h.overall_status in ('ALERT', 'DANGER')
      then h.hour_start_ns
      else null
    end) as first_detection_ts,
    t.expected_reasons
  from truth t
  left join health_hourly h on t.device_id = (select device_id from {{ ref('dim_asset') }} where asset_id = t.asset_id limit 1)
  group by 1, 2, 3, 4, 5, 6, 7
),

-- Calculate lead time
with_lead_time as (
  select
    label_id,
    asset_id,
    scenario,
    case when first_detection_ts is not null then true else false end as detected,
    first_detection_ts,
    failure_ts,
    case
      when first_detection_ts is not null
        then (failure_ts - first_detection_ts) / 3.6e12  -- nanoseconds to hours
        else null
    end as lead_time_hours,
    expected_reasons,
    current_timestamp() as evaluated_at,
    '1.0' as rules_version
  from detections
)

select * from with_lead_time
