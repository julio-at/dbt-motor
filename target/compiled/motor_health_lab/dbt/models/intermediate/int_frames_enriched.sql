

-- Frames enriched with physics calculations
with frames as (
  select * from "motor_health_lab"."raw_staging"."stg_frames"
),

drive_telemetry as (
  select * from "motor_health_lab"."raw_staging"."stg_drive_telemetry"
),

-- Simple left join to latest available drive data per device
joined as (
  select
    f.frame_id,
    f.timestamp_ns,
    f.device_id,
    f.floor,
    f.tandem,
    f.order_pos,
    f.x_amplitude_um_pp,
    f.x_frequency_hz,
    f.y_amplitude_um_pp,
    f.y_frequency_hz,
    f.z_amplitude_um_pp,
    f.z_frequency_hz,
    f.temperature_c,
    f.relative_humidity_pct,
    d.output_hz,
    d.power_factor,
    d.run_state
  from frames f
  left join lateral (
    select output_hz, power_factor, run_state
    from drive_telemetry
    where drive_id like 'VFD-%'  -- Generic match
    order by timestamp_ns desc
    limit 1
  ) d on true
),

enriched as (
  select
    frame_id,
    timestamp_ns,
    device_id,
    floor,
    tandem,
    order_pos,
    x_amplitude_um_pp,
    x_frequency_hz,
    y_amplitude_um_pp,
    y_frequency_hz,
    z_amplitude_um_pp,
    z_frequency_hz,
    temperature_c,
    relative_humidity_pct,
    coalesce(output_hz, 0) as output_hz,
    coalesce(power_factor, 0.85) as power_factor,
    coalesce(run_state, 'UNKNOWN') as run_state,
    -- Calculate running speed (SPEC §4.2, assuming 4 poles)
    coalesce(output_hz, 0) * 2 / 4 as f_sync_hz,
    coalesce(output_hz, 0) * 2 / 4 * (1 - 0.02) as f_1x_hz,
    floor(coalesce(output_hz, 0) / 5)::int as speed_band,
    -- Calculate velocity RMS (SPEC §4.1)
    case when x_frequency_hz > 0
      then 2.2214e-3 * x_frequency_hz * x_amplitude_um_pp
      else 0
    end as x_v_rms_mm_s,
    case when y_frequency_hz > 0
      then 2.2214e-3 * y_frequency_hz * y_amplitude_um_pp
      else 0
    end as y_v_rms_mm_s,
    case when z_frequency_hz > 0
      then 2.2214e-3 * z_frequency_hz * z_amplitude_um_pp
      else 0
    end as z_v_rms_mm_s,
    -- Synchronous check (SPEC §4.3)
    case
      when f_1x_hz > 0 then x_frequency_hz / f_1x_hz
      else 0
    end as x_k
  from joined
)

select * from enriched