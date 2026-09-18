
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select label_id
from "motor_health_lab"."raw"."truth_labels"
where label_id is null



  
  
      
    ) dbt_internal_test