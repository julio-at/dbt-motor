
    
    

select
    label_id as unique_field,
    count(*) as n_records

from "motor_health_lab"."raw"."truth_labels"
where label_id is not null
group by label_id
having count(*) > 1


