
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select timestamp
from "motor_health_lab"."raw"."spectra"
where timestamp is null



  
  
      
    ) dbt_internal_test