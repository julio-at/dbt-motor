

-- Asset dimension: one row per asset (slowly changing)
select
  asset_id,
  device_id,
  asset_type,
  drive_id,
  plant_id,
  poles,
  rated_kw,
  rated_current_a,
  iso_group,
  foundation,
  nominal_output_hz,
  bearing_de,
  bearing_nde,
  relube_interval_h,
  installed_at::timestamp_ns as installed_at
from "motor_health_lab"."raw_seeds"."asset_registry"