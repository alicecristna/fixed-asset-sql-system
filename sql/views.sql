CREATE VIEW v_invoice_capitalization_reconciliation AS
SELECT
    invoice.invoice_id,
    vendor.vendor_code,
    vendor.vendor_name,
    invoice.invoice_number,
    invoice.invoice_date,
    invoice.currency,
    invoice.net_amount_cents,
    invoice.vat_amount_cents,
    invoice.recoverable_vat_cents,
    invoice.gross_amount_cents,
    invoice.capitalizable_amount_cents,
    COUNT(asset.asset_id) AS asset_count,
    COALESCE(SUM(asset.acquisition_cost_cents), 0) AS asset_cost_cents,
    invoice.capitalizable_amount_cents
        - COALESCE(SUM(asset.acquisition_cost_cents), 0) AS difference_cents,
    CASE
        WHEN invoice.capitalizable_amount_cents
             = COALESCE(SUM(asset.acquisition_cost_cents), 0)
        THEN 'MATCH'
        ELSE 'MISMATCH'
    END AS reconciliation_status
FROM supplier_invoices AS invoice
JOIN vendors AS vendor
    ON vendor.vendor_id = invoice.vendor_id
LEFT JOIN fixed_assets AS asset
    ON asset.invoice_id = invoice.invoice_id
GROUP BY
    invoice.invoice_id,
    vendor.vendor_code,
    vendor.vendor_name,
    invoice.invoice_number,
    invoice.invoice_date,
    invoice.currency,
    invoice.net_amount_cents,
    invoice.vat_amount_cents,
    invoice.recoverable_vat_cents,
    invoice.gross_amount_cents,
    invoice.capitalizable_amount_cents;

CREATE VIEW v_asset_assignment_intervals AS
WITH assignment_sequence AS (
    SELECT
        assignment.assignment_id,
        assignment.asset_id,
        assignment.department_id,
        assignment.custodian_employee_id,
        assignment.location,
        assignment.effective_from,
        LEAD(assignment.effective_from) OVER (
            PARTITION BY assignment.asset_id
            ORDER BY assignment.effective_from, assignment.assignment_id
        ) AS next_effective_from
    FROM asset_assignments AS assignment
)
SELECT
    sequence.assignment_id,
    sequence.asset_id,
    asset.asset_tag,
    asset.asset_name,
    sequence.department_id,
    department.department_code,
    department.department_name,
    sequence.custodian_employee_id,
    employee.employee_code AS custodian_employee_code,
    employee.employee_name AS custodian_employee_name,
    sequence.location,
    sequence.effective_from,
    sequence.next_effective_from,
    CASE
        WHEN sequence.next_effective_from IS NOT NULL
        THEN date(sequence.next_effective_from, '-1 day')
        ELSE disposal.disposal_date
    END AS effective_to
FROM assignment_sequence AS sequence
JOIN fixed_assets AS asset
    ON asset.asset_id = sequence.asset_id
JOIN departments AS department
    ON department.department_id = sequence.department_id
JOIN employees AS employee
    ON employee.employee_id = sequence.custodian_employee_id
LEFT JOIN asset_disposals AS disposal
    ON disposal.asset_id = sequence.asset_id;

CREATE VIEW v_depreciation_schedule AS
WITH RECURSIVE
asset_terms AS (
    SELECT
        asset.asset_id,
        asset.asset_tag,
        asset.asset_name,
        asset.acquisition_cost_cents,
        asset.residual_value_cents,
        asset.useful_life_months,
        asset.acquisition_cost_cents - asset.residual_value_cents
            AS depreciable_amount_cents,
        disposal.disposal_date,
        date(asset.in_service_date, 'start of month', '+1 month')
            AS first_depreciation_month
    FROM fixed_assets AS asset
    LEFT JOIN asset_disposals AS disposal
        ON disposal.asset_id = asset.asset_id
),
depreciation_periods (
    asset_id,
    asset_tag,
    asset_name,
    acquisition_cost_cents,
    residual_value_cents,
    useful_life_months,
    depreciable_amount_cents,
    disposal_date,
    depreciation_month,
    period_number
) AS (
    SELECT
        terms.asset_id,
        terms.asset_tag,
        terms.asset_name,
        terms.acquisition_cost_cents,
        terms.residual_value_cents,
        terms.useful_life_months,
        terms.depreciable_amount_cents,
        terms.disposal_date,
        terms.first_depreciation_month,
        1
    FROM asset_terms AS terms
    WHERE terms.disposal_date IS NULL
       OR terms.first_depreciation_month
          <= date(terms.disposal_date, 'start of month')

    UNION ALL

    SELECT
        periods.asset_id,
        periods.asset_tag,
        periods.asset_name,
        periods.acquisition_cost_cents,
        periods.residual_value_cents,
        periods.useful_life_months,
        periods.depreciable_amount_cents,
        periods.disposal_date,
        date(periods.depreciation_month, '+1 month'),
        periods.period_number + 1
    FROM depreciation_periods AS periods
    WHERE periods.period_number < periods.useful_life_months
      AND (
          periods.disposal_date IS NULL
          OR date(periods.depreciation_month, '+1 month')
             <= date(periods.disposal_date, 'start of month')
      )
),
monthly_charges AS (
    SELECT
        periods.*,
        (periods.depreciable_amount_cents / periods.useful_life_months)
        + CASE
            WHEN periods.period_number
                 <= periods.depreciable_amount_cents
                    % periods.useful_life_months
            THEN 1
            ELSE 0
          END AS monthly_depreciation_cents
    FROM depreciation_periods AS periods
),
schedule_with_accumulation AS (
    SELECT
        charges.*,
        SUM(charges.monthly_depreciation_cents) OVER (
            PARTITION BY charges.asset_id
            ORDER BY charges.period_number
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS accumulated_depreciation_cents
    FROM monthly_charges AS charges
)
SELECT
    asset_id,
    asset_tag,
    asset_name,
    depreciation_month,
    period_number,
    useful_life_months,
    acquisition_cost_cents,
    residual_value_cents,
    depreciable_amount_cents,
    monthly_depreciation_cents,
    accumulated_depreciation_cents,
    max(
        residual_value_cents,
        acquisition_cost_cents - accumulated_depreciation_cents
    ) AS net_book_value_cents,
    disposal_date
FROM schedule_with_accumulation;
