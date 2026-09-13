SELECT
    asset_id,
    asset_tag,
    asset_name,
    assignment_id,
    department_code,
    department_name,
    custodian_employee_code,
    custodian_employee_name,
    location,
    effective_from,
    effective_to
FROM v_asset_assignment_intervals
ORDER BY asset_tag, effective_from, assignment_id;
