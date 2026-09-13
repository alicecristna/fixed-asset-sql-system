WITH
parameters AS (
    SELECT '2026-12-31' AS as_of_date
),
depreciation_as_of AS (
    SELECT
        schedule.asset_id,
        MAX(schedule.accumulated_depreciation_cents)
            AS accumulated_depreciation_cents
    FROM v_depreciation_schedule AS schedule
    CROSS JOIN parameters
    WHERE schedule.depreciation_month
          <= date(parameters.as_of_date, 'start of month')
    GROUP BY schedule.asset_id
),
asset_reporting_cutoff AS (
    SELECT
        asset.asset_id,
        parameters.as_of_date,
        CASE
            WHEN disposal.disposal_date IS NOT NULL
                 AND disposal.disposal_date <= parameters.as_of_date
            THEN disposal.disposal_date
            ELSE parameters.as_of_date
        END AS assignment_cutoff_date
    FROM fixed_assets AS asset
    CROSS JOIN parameters
    LEFT JOIN asset_disposals AS disposal
        ON disposal.asset_id = asset.asset_id
),
assignment_as_of AS (
    SELECT
        cutoff.asset_id,
        history.department_code,
        history.department_name,
        history.custodian_employee_code,
        history.custodian_employee_name,
        history.location
    FROM asset_reporting_cutoff AS cutoff
    LEFT JOIN v_asset_assignment_intervals AS history
        ON history.asset_id = cutoff.asset_id
       AND history.effective_from <= cutoff.assignment_cutoff_date
       AND (
           history.effective_to IS NULL
           OR history.effective_to >= cutoff.assignment_cutoff_date
       )
)
SELECT
    parameters.as_of_date,
    asset.asset_id,
    asset.asset_tag,
    asset.asset_name,
    category.category_code,
    category.category_name,
    invoice.invoice_number,
    invoice.currency,
    asset.in_service_date,
    asset.acquisition_cost_cents,
    asset.residual_value_cents,
    asset.useful_life_months,
    CASE
        WHEN disposal.disposal_date IS NOT NULL
             AND disposal.disposal_date <= parameters.as_of_date
        THEN 'DISPOSED'
        ELSE 'ACTIVE'
    END AS asset_status,
    disposal.disposal_date,
    COALESCE(depreciation.accumulated_depreciation_cents, 0)
        AS accumulated_depreciation_cents,
    max(
        asset.residual_value_cents,
        asset.acquisition_cost_cents
            - COALESCE(depreciation.accumulated_depreciation_cents, 0)
    ) AS net_book_value_cents,
    assignment.department_code,
    assignment.department_name,
    assignment.custodian_employee_code,
    assignment.custodian_employee_name,
    assignment.location
FROM fixed_assets AS asset
CROSS JOIN parameters
JOIN asset_categories AS category
    ON category.category_id = asset.category_id
JOIN supplier_invoices AS invoice
    ON invoice.invoice_id = asset.invoice_id
LEFT JOIN asset_disposals AS disposal
    ON disposal.asset_id = asset.asset_id
   AND disposal.disposal_date <= parameters.as_of_date
LEFT JOIN depreciation_as_of AS depreciation
    ON depreciation.asset_id = asset.asset_id
LEFT JOIN assignment_as_of AS assignment
    ON assignment.asset_id = asset.asset_id
WHERE asset.in_service_date <= parameters.as_of_date
ORDER BY asset.asset_tag;
