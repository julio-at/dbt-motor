

-- Vibration frames: rename to snake_case, cast types, parse coordinates, dedup
with source as (
  select * from "motor_health_lab"."raw"."vibration_frames"
),

renamed as (
  select
    timestamp::timestamp_ns as timestamp_ns,
    device_id,
    x_amplitude_um_pp,
    x_frequency_hz,
    y_amplitude_um_pp,
    y_frequency_hz,
    z_amplitude_um_pp,
    z_frequency_hz,
    temperature_c,
    relative_humidity_pct,
    coordinates_position,
    _file_name,
    _file_row,
    _loaded_at::timestamp_ns as loaded_at
  from source
),

parsed as (
  select
    timestamp_ns,
    device_id,
    x_amplitude_um_pp,
    x_frequency_hz,
    y_amplitude_um_pp,
    y_frequency_hz,
    z_amplitude_um_pp,
    z_frequency_hz,
    temperature_c,
    relative_humidity_pct,
    -- Parse coordinates "[floor,tandem,order]" to individual columns
    cast(string_split(trim(coordinates_position, '[]'), ',')[1] as int) as floor,
    cast(string_split(trim(coordinates_position, '[]'), ',')[2] as int) as tandem,
    cast(string_split(trim(coordinates_position, '[]'), ',')[3] as int) as order_pos,
    _file_name,
    _file_row,
    loaded_at
  from renamed
),

deduped as (
  select
    row_number() over (order by timestamp_ns, device_id) as frame_id,
    *
  from parsed
  qualify row_number() over (partition by device_id, timestamp_ns order by loaded_at) = 1
)

select * from deduped