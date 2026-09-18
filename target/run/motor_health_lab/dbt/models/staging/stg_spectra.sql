
  
  create view "motor_health_lab"."raw_staging"."stg_spectra__dbt_tmp" as (
    

-- Spectra: rename, cast, keep bins as array
with source as (
  select * from "motor_health_lab"."raw"."spectra"
),

renamed as (
  select
    timestamp::timestamp_ns as timestamp_ns,
    device_id,
    axis,
    fs_hz,
    n_samples,
    "window",
    df_hz,
    f_max_hz,
    unit,
    bins,  -- Keep as DOUBLE[] array for FFT bins
    _file_name,
    _file_row,
    _loaded_at::timestamp_ns as loaded_at
  from source
),

validated as (
  select
    row_number() over (order by timestamp_ns, device_id, axis) as spectrum_id,
    *
  from renamed
  where axis in ('X', 'Y', 'Z')
    and array_length(bins) > 0
)

select * from validated
  );
