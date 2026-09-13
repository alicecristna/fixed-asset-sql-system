-- SQLite 3.37+ is required for STRICT tables.
-- Dates use an intentionally small ISO-8601 validation rule: YYYY-MM-DD with
-- month 01-12 and day 01-31. Calendar-specific validation is out of scope.

CREATE TABLE departments (
    department_id INTEGER PRIMARY KEY,
    department_code TEXT NOT NULL UNIQUE
        CHECK (length(trim(department_code)) > 0),
    department_name TEXT NOT NULL UNIQUE
        CHECK (length(trim(department_name)) > 0)
) STRICT;

CREATE TABLE employees (
    employee_id INTEGER PRIMARY KEY,
    employee_code TEXT NOT NULL UNIQUE
        CHECK (length(trim(employee_code)) > 0),
    employee_name TEXT NOT NULL
        CHECK (length(trim(employee_name)) > 0),
    department_id INTEGER NOT NULL,
    employment_status TEXT NOT NULL DEFAULT 'ACTIVE'
        CHECK (employment_status IN ('ACTIVE', 'INACTIVE')),
    FOREIGN KEY (department_id)
        REFERENCES departments (department_id)
        ON DELETE RESTRICT
) STRICT;

CREATE TABLE vendors (
    vendor_id INTEGER PRIMARY KEY,
    vendor_code TEXT NOT NULL UNIQUE
        CHECK (length(trim(vendor_code)) > 0),
    vendor_name TEXT NOT NULL
        CHECK (length(trim(vendor_name)) > 0)
) STRICT;

CREATE TABLE supplier_invoices (
    invoice_id INTEGER PRIMARY KEY,
    vendor_id INTEGER NOT NULL,
    invoice_number TEXT NOT NULL
        CHECK (length(trim(invoice_number)) > 0),
    invoice_date TEXT NOT NULL
        CHECK (
            length(invoice_date) = 10
            AND invoice_date GLOB
                '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'
            AND substr(invoice_date, 6, 2) BETWEEN '01' AND '12'
            AND substr(invoice_date, 9, 2) BETWEEN '01' AND '31'
        ),
    currency TEXT NOT NULL DEFAULT 'CNY'
        CHECK (currency = 'CNY'),
    net_amount_cents INTEGER NOT NULL
        CHECK (
            typeof(net_amount_cents) = 'integer'
            AND net_amount_cents > 0
        ),
    vat_amount_cents INTEGER NOT NULL
        CHECK (
            typeof(vat_amount_cents) = 'integer'
            AND vat_amount_cents >= 0
        ),
    recoverable_vat_cents INTEGER NOT NULL
        CHECK (
            typeof(recoverable_vat_cents) = 'integer'
            AND recoverable_vat_cents BETWEEN 0 AND vat_amount_cents
        ),
    gross_amount_cents INTEGER GENERATED ALWAYS AS (
        net_amount_cents + vat_amount_cents
    ) STORED,
    capitalizable_amount_cents INTEGER GENERATED ALWAYS AS (
        net_amount_cents + vat_amount_cents - recoverable_vat_cents
    ) STORED,
    UNIQUE (vendor_id, invoice_number),
    FOREIGN KEY (vendor_id)
        REFERENCES vendors (vendor_id)
        ON DELETE RESTRICT
) STRICT;

CREATE TABLE asset_categories (
    category_id INTEGER PRIMARY KEY,
    category_code TEXT NOT NULL UNIQUE
        CHECK (length(trim(category_code)) > 0),
    category_name TEXT NOT NULL UNIQUE
        CHECK (length(trim(category_name)) > 0)
) STRICT;

CREATE TABLE fixed_assets (
    asset_id INTEGER PRIMARY KEY,
    asset_tag TEXT NOT NULL UNIQUE
        CHECK (length(trim(asset_tag)) > 0),
    invoice_id INTEGER NOT NULL,
    category_id INTEGER NOT NULL,
    asset_name TEXT NOT NULL
        CHECK (length(trim(asset_name)) > 0),
    acquisition_cost_cents INTEGER NOT NULL
        CHECK (
            typeof(acquisition_cost_cents) = 'integer'
            AND acquisition_cost_cents > 0
        ),
    residual_value_cents INTEGER NOT NULL DEFAULT 0
        CHECK (
            typeof(residual_value_cents) = 'integer'
            AND residual_value_cents >= 0
            AND residual_value_cents < acquisition_cost_cents
        ),
    useful_life_months INTEGER NOT NULL
        CHECK (
            typeof(useful_life_months) = 'integer'
            AND useful_life_months > 0
        ),
    in_service_date TEXT NOT NULL
        CHECK (
            length(in_service_date) = 10
            AND in_service_date GLOB
                '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'
            AND substr(in_service_date, 6, 2) BETWEEN '01' AND '12'
            AND substr(in_service_date, 9, 2) BETWEEN '01' AND '31'
        ),
    FOREIGN KEY (invoice_id)
        REFERENCES supplier_invoices (invoice_id)
        ON DELETE RESTRICT,
    FOREIGN KEY (category_id)
        REFERENCES asset_categories (category_id)
        ON DELETE RESTRICT
) STRICT;

CREATE TABLE asset_assignments (
    assignment_id INTEGER PRIMARY KEY,
    asset_id INTEGER NOT NULL,
    department_id INTEGER NOT NULL,
    custodian_employee_id INTEGER NOT NULL,
    location TEXT NOT NULL
        CHECK (length(trim(location)) > 0),
    effective_from TEXT NOT NULL
        CHECK (
            length(effective_from) = 10
            AND effective_from GLOB
                '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'
            AND substr(effective_from, 6, 2) BETWEEN '01' AND '12'
            AND substr(effective_from, 9, 2) BETWEEN '01' AND '31'
        ),
    UNIQUE (asset_id, effective_from),
    FOREIGN KEY (asset_id)
        REFERENCES fixed_assets (asset_id)
        ON DELETE RESTRICT,
    FOREIGN KEY (department_id)
        REFERENCES departments (department_id)
        ON DELETE RESTRICT,
    FOREIGN KEY (custodian_employee_id)
        REFERENCES employees (employee_id)
        ON DELETE RESTRICT
) STRICT;

CREATE TABLE asset_disposals (
    asset_id INTEGER PRIMARY KEY,
    disposal_date TEXT NOT NULL
        CHECK (
            length(disposal_date) = 10
            AND disposal_date GLOB
                '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'
            AND substr(disposal_date, 6, 2) BETWEEN '01' AND '12'
            AND substr(disposal_date, 9, 2) BETWEEN '01' AND '31'
        ),
    disposal_method TEXT NOT NULL
        CHECK (disposal_method IN ('SALE', 'SCRAP', 'DONATION')),
    proceeds_cents INTEGER NOT NULL DEFAULT 0
        CHECK (
            typeof(proceeds_cents) = 'integer'
            AND proceeds_cents >= 0
        ),
    approved_by_employee_id INTEGER NOT NULL,
    note TEXT
        CHECK (note IS NULL OR length(trim(note)) > 0),
    FOREIGN KEY (asset_id)
        REFERENCES fixed_assets (asset_id)
        ON DELETE RESTRICT,
    FOREIGN KEY (approved_by_employee_id)
        REFERENCES employees (employee_id)
        ON DELETE RESTRICT
) STRICT;

CREATE INDEX idx_employees_department
    ON employees (department_id);
CREATE INDEX idx_supplier_invoices_vendor
    ON supplier_invoices (vendor_id);
CREATE INDEX idx_fixed_assets_invoice
    ON fixed_assets (invoice_id);
CREATE INDEX idx_fixed_assets_category
    ON fixed_assets (category_id);
CREATE INDEX idx_asset_assignments_department
    ON asset_assignments (department_id);
CREATE INDEX idx_asset_assignments_custodian
    ON asset_assignments (custodian_employee_id);
CREATE INDEX idx_asset_disposals_approver
    ON asset_disposals (approved_by_employee_id);

CREATE TRIGGER trg_fixed_assets_validate_insert
BEFORE INSERT ON fixed_assets
BEGIN
    SELECT RAISE(ABORT, 'in-service date cannot precede invoice date')
    WHERE NEW.in_service_date < (
        SELECT invoice_date
        FROM supplier_invoices
        WHERE invoice_id = NEW.invoice_id
    );
END;

CREATE TRIGGER trg_fixed_assets_validate_update
BEFORE UPDATE OF invoice_id, in_service_date ON fixed_assets
BEGIN
    SELECT RAISE(ABORT, 'in-service date cannot precede invoice date')
    WHERE NEW.in_service_date < (
        SELECT invoice_date
        FROM supplier_invoices
        WHERE invoice_id = NEW.invoice_id
    );

    SELECT RAISE(ABORT, 'in-service date cannot follow an assignment')
    WHERE EXISTS (
        SELECT 1
        FROM asset_assignments
        WHERE asset_id = OLD.asset_id
          AND effective_from < NEW.in_service_date
    );

    SELECT RAISE(ABORT, 'in-service date cannot follow disposal')
    WHERE EXISTS (
        SELECT 1
        FROM asset_disposals
        WHERE asset_id = OLD.asset_id
          AND disposal_date < NEW.in_service_date
    );
END;

CREATE TRIGGER trg_supplier_invoices_protect_asset_dates
BEFORE UPDATE OF invoice_date ON supplier_invoices
BEGIN
    SELECT RAISE(ABORT, 'invoice date cannot follow an asset in-service date')
    WHERE EXISTS (
        SELECT 1
        FROM fixed_assets
        WHERE invoice_id = OLD.invoice_id
          AND in_service_date < NEW.invoice_date
    );
END;

CREATE TRIGGER trg_asset_assignments_validate_insert
BEFORE INSERT ON asset_assignments
BEGIN
    SELECT RAISE(ABORT, 'assignment date cannot precede in-service date')
    WHERE NEW.effective_from < (
        SELECT in_service_date
        FROM fixed_assets
        WHERE asset_id = NEW.asset_id
    );

    SELECT RAISE(ABORT, 'assignment date cannot follow disposal')
    WHERE EXISTS (
        SELECT 1
        FROM asset_disposals
        WHERE asset_id = NEW.asset_id
          AND disposal_date < NEW.effective_from
    );
END;

CREATE TRIGGER trg_asset_assignments_validate_update
BEFORE UPDATE OF asset_id, effective_from ON asset_assignments
BEGIN
    SELECT RAISE(ABORT, 'assignment date cannot precede in-service date')
    WHERE NEW.effective_from < (
        SELECT in_service_date
        FROM fixed_assets
        WHERE asset_id = NEW.asset_id
    );

    SELECT RAISE(ABORT, 'assignment date cannot follow disposal')
    WHERE EXISTS (
        SELECT 1
        FROM asset_disposals
        WHERE asset_id = NEW.asset_id
          AND disposal_date < NEW.effective_from
    );
END;

CREATE TRIGGER trg_asset_disposals_validate_insert
BEFORE INSERT ON asset_disposals
BEGIN
    SELECT RAISE(ABORT, 'disposal date cannot precede in-service date')
    WHERE NEW.disposal_date < (
        SELECT in_service_date
        FROM fixed_assets
        WHERE asset_id = NEW.asset_id
    );

    SELECT RAISE(ABORT, 'disposal date cannot precede an assignment')
    WHERE EXISTS (
        SELECT 1
        FROM asset_assignments
        WHERE asset_id = NEW.asset_id
          AND effective_from > NEW.disposal_date
    );
END;

CREATE TRIGGER trg_asset_disposals_validate_update
BEFORE UPDATE OF asset_id, disposal_date ON asset_disposals
BEGIN
    SELECT RAISE(ABORT, 'disposal date cannot precede in-service date')
    WHERE NEW.disposal_date < (
        SELECT in_service_date
        FROM fixed_assets
        WHERE asset_id = NEW.asset_id
    );

    SELECT RAISE(ABORT, 'disposal date cannot precede an assignment')
    WHERE EXISTS (
        SELECT 1
        FROM asset_assignments
        WHERE asset_id = NEW.asset_id
          AND effective_from > NEW.disposal_date
    );
END;
