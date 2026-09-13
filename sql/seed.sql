-- Every person, organization, identifier, location, and date below is
-- synthetic and exists only to make the demonstration deterministic.

INSERT INTO departments (
    department_id,
    department_code,
    department_name
) VALUES
    (1, 'FIN', 'Synthetic Finance'),
    (2, 'IT',  'Synthetic Information Technology'),
    (3, 'OPS', 'Synthetic Operations');

INSERT INTO employees (
    employee_id,
    employee_code,
    employee_name,
    department_id,
    employment_status
) VALUES
    (1, 'SYN-FIN-001', 'Synthetic Employee A', 1, 'ACTIVE'),
    (2, 'SYN-IT-001',  'Synthetic Employee B', 2, 'ACTIVE'),
    (3, 'SYN-IT-002',  'Synthetic Employee C', 2, 'ACTIVE'),
    (4, 'SYN-OPS-001', 'Synthetic Employee D', 3, 'ACTIVE'),
    (5, 'SYN-FIN-002', 'Synthetic Employee E', 1, 'ACTIVE');

INSERT INTO vendors (
    vendor_id,
    vendor_code,
    vendor_name
) VALUES
    (1, 'SYN-VENDOR-IT',   'Synthetic Technology Vendor'),
    (2, 'SYN-VENDOR-HVAC', 'Synthetic Building Systems Vendor'),
    (3, 'SYN-VENDOR-AUTO', 'Synthetic Mobility Vendor');

INSERT INTO supplier_invoices (
    invoice_id,
    vendor_id,
    invoice_number,
    invoice_date,
    currency,
    net_amount_cents,
    vat_amount_cents,
    recoverable_vat_cents
) VALUES
    (1, 1, 'SYN-IT-2024-001',   '2024-01-10', 'CNY',  2400000,  312000,  312000),
    (2, 2, 'SYN-HVAC-2024-001', '2024-06-10', 'CNY', 15000000, 1950000, 1950000),
    (3, 3, 'SYN-VEH-2024-001',  '2024-07-15', 'CNY', 22000000, 2860000, 2860000);

INSERT INTO asset_categories (
    category_id,
    category_code,
    category_name
) VALUES
    (1, 'IT-EQUIPMENT',     'Synthetic IT Equipment'),
    (2, 'BUILDING-SYSTEMS', 'Synthetic Building Systems'),
    (3, 'VEHICLES',         'Synthetic Vehicles');

INSERT INTO fixed_assets (
    asset_id,
    asset_tag,
    invoice_id,
    category_id,
    asset_name,
    acquisition_cost_cents,
    residual_value_cents,
    useful_life_months,
    in_service_date
) VALUES
    (1, 'SYN-IT-0001', 1, 1, 'Synthetic Analytics Workstation A',
        1199999, 119999, 36, '2024-01-20'),
    (2, 'SYN-IT-0002', 1, 1, 'Synthetic Analytics Workstation B',
        1200001, 120000, 36, '2024-01-20'),
    (3, 'SYN-HVAC-0001', 2, 2, 'Synthetic Headquarters HVAC System',
        15000000, 750000, 120, '2024-06-20'),
    (4, 'SYN-VEH-0001', 3, 3, 'Synthetic Electric Fleet Vehicle',
        22000000, 1100000, 60, '2024-08-01');

INSERT INTO asset_assignments (
    assignment_id,
    asset_id,
    department_id,
    custodian_employee_id,
    location,
    effective_from
) VALUES
    (1, 1, 2, 2, 'Synthetic HQ - IT Lab', '2024-01-20'),
    (2, 1, 1, 1, 'Synthetic HQ - Finance Analytics', '2025-07-01'),
    (3, 2, 2, 3, 'Synthetic HQ - IT Lab', '2024-01-20'),
    (4, 3, 3, 4, 'Synthetic HQ - Plant Room', '2024-06-20'),
    (5, 4, 3, 4, 'Synthetic HQ - Fleet Bay', '2024-08-01');

INSERT INTO asset_disposals (
    asset_id,
    disposal_date,
    disposal_method,
    proceeds_cents,
    approved_by_employee_id,
    note
) VALUES (
    4,
    '2026-09-15',
    'SALE',
    15000000,
    5,
    'Synthetic sale used for the deterministic demonstration'
);
