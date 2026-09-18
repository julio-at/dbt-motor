
  
  create view "motor_health_lab"."raw_staging"."stg_drive_telemetry__dbt_tmp" as (
    

-- Drive telemetry: rename, cast, validate
with source as (
  select * from "motor_health_lab"."raw"."drive_telemetry"
),

renamed as (
  select
    timestamp::timestamp_ns as timestamp_ns,
    drive_id,
    output_hz,
    voltage_l1l2_v,
    voltage_l2l3_v,
    voltage_l3l1_v,
    current_l1_a,
    current_l2_a,
    current_l3_a,
    phase_angle_l1_deg,
    phase_angle_l2_deg,
    phase_angle_l3_deg,
    power_factor,
    run_state,
    _file_name,
    _file_row,
    _loaded_at::timestamp_ns as loaded_at
  from source
),

validated as (
  select
    row_number() over (order by timestamp_ns, drive_id) as telemetry_id,
    *
  from renamed
  where power_factor > 0 and power_factor <= 1  -- Valid PF range
)

select * from validated
  );
