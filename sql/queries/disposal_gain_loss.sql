WITH depreciation_at_disposal AS (
    SELECT
        disposal.asset_id,
        MAX(schedule.accumulated_depreciation_cents)
            AS accumulated_depreciation_cents
    FROM asset_disposals AS disposal
    LEFT JOIN v_depreciation_schedule AS schedule
        ON schedule.asset_id = disposal.asset_id
       AND schedule.depreciation_month
           <= date(disposal.disposal_date, 'start of month')
    GROUP BY disposal.asset_id
),
disposal_values AS (
    SELECT
        asset.asset_id,
        asset.asset_tag,
        asset.asset_name,
        disposal.disposal_date,
        disposal.disposal_method,
        disposal.proceeds_cents,
        disposal.approved_by_employee_id,
        disposal.note,
        asset.acquisition_cost_cents,
        asset.residual_value_cents,
        COALESCE(depreciation.accumulated_depreciation_cents, 0)
            AS accumulated_depreciation_cents,
        max(
            asset.residual_value_cents,
            asset.acquisition_cost_cents
                - COALESCE(depreciation.accumulated_depreciation_cents, 0)
        ) AS net_book_value_at_disposal_cents
    FROM asset_disposals AS disposal
    JOIN fixed_assets AS asset
        ON asset.asset_id = disposal.asset_id
    LEFT JOIN depreciation_at_disposal AS depreciation
        ON depreciation.asset_id = disposal.asset_id
)
SELECT
    values_at_disposal.asset_id,
    values_at_disposal.asset_tag,
    values_at_disposal.asset_name,
    values_at_disposal.disposal_date,
    values_at_disposal.disposal_method,
    values_at_disposal.acquisition_cost_cents,
    values_at_disposal.accumulated_depreciation_cents,
    values_at_disposal.net_book_value_at_disposal_cents,
    values_at_disposal.proceeds_cents,
    values_at_disposal.proceeds_cents
        - values_at_disposal.net_book_value_at_disposal_cents
        AS gain_loss_cents,
    approver.employee_code AS approved_by_employee_code,
    approver.employee_name AS approved_by_employee_name,
    values_at_disposal.note
FROM disposal_values AS values_at_disposal
JOIN employees AS approver
    ON approver.employee_id = values_at_disposal.approved_by_employee_id
ORDER BY values_at_disposal.disposal_date, values_at_disposal.asset_tag;
