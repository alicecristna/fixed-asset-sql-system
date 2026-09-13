SELECT
    invoice_id,
    vendor_code,
    vendor_name,
    invoice_number,
    invoice_date,
    currency,
    capitalizable_amount_cents,
    asset_count,
    asset_cost_cents,
    difference_cents,
    reconciliation_status
FROM v_invoice_capitalization_reconciliation
ORDER BY invoice_date, vendor_code, invoice_number;
