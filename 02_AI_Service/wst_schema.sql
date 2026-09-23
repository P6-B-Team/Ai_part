-- WST database schema (PostgreSQL) — combined from migrations 001..005, in order
-- Generated for delivery. Source of truth: src/db/migrations/*.sql

-- ============ 001_init.sql ============
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE TABLE IF NOT EXISTS organizations(id uuid PRIMARY KEY DEFAULT gen_random_uuid(), name text NOT NULL, created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS users(id uuid PRIMARY KEY DEFAULT gen_random_uuid(), organization_id uuid NOT NULL REFERENCES organizations(id), email text NOT NULL, password_hash text NOT NULL, display_name text NOT NULL, locale text NOT NULL DEFAULT 'en', is_active boolean NOT NULL DEFAULT true, created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(organization_id,email));
CREATE TABLE IF NOT EXISTS roles(id uuid PRIMARY KEY DEFAULT gen_random_uuid(), code text UNIQUE NOT NULL);
CREATE TABLE IF NOT EXISTS permissions(id uuid PRIMARY KEY DEFAULT gen_random_uuid(), code text UNIQUE NOT NULL);
CREATE TABLE IF NOT EXISTS user_roles(user_id uuid REFERENCES users(id) ON DELETE CASCADE, role_id uuid REFERENCES roles(id) ON DELETE CASCADE, PRIMARY KEY(user_id,role_id));
CREATE TABLE IF NOT EXISTS role_permissions(role_id uuid REFERENCES roles(id) ON DELETE CASCADE, permission_id uuid REFERENCES permissions(id) ON DELETE CASCADE, PRIMARY KEY(role_id,permission_id));
CREATE TABLE IF NOT EXISTS refresh_tokens(id uuid PRIMARY KEY DEFAULT gen_random_uuid(), user_id uuid REFERENCES users(id) ON DELETE CASCADE, token_hash text NOT NULL, expires_at timestamptz NOT NULL, revoked_at timestamptz);
CREATE TABLE IF NOT EXISTS customers(id uuid PRIMARY KEY DEFAULT gen_random_uuid(), organization_id uuid REFERENCES organizations(id), name text NOT NULL, phone text, email text, preferred_contact text, status text NOT NULL DEFAULT 'ACTIVE', created_at timestamptz DEFAULT now(), updated_at timestamptz DEFAULT now());
CREATE TABLE IF NOT EXISTS vehicles(id uuid PRIMARY KEY DEFAULT gen_random_uuid(), organization_id uuid REFERENCES organizations(id), customer_id uuid NOT NULL REFERENCES customers(id), plate_no text NOT NULL, vin text NOT NULL, make text NOT NULL, model text NOT NULL, year int, mileage int NOT NULL DEFAULT 0, status text NOT NULL DEFAULT 'ACTIVE', UNIQUE(organization_id,plate_no), UNIQUE(organization_id,vin));
CREATE TABLE IF NOT EXISTS bays(id uuid PRIMARY KEY DEFAULT gen_random_uuid(), organization_id uuid REFERENCES organizations(id), code text NOT NULL, name text NOT NULL, active boolean DEFAULT true, UNIQUE(organization_id,code));
CREATE TABLE IF NOT EXISTS job_cards(id uuid PRIMARY KEY DEFAULT gen_random_uuid(), organization_id uuid REFERENCES organizations(id), job_no text NOT NULL, customer_id uuid REFERENCES customers(id), vehicle_id uuid REFERENCES vehicles(id), complaint text NOT NULL, service_type text NOT NULL, priority text NOT NULL DEFAULT 'NORMAL', received_mileage int NOT NULL, expected_at timestamptz, bay_id uuid REFERENCES bays(id), assigned_technician_id uuid REFERENCES users(id), status text NOT NULL DEFAULT 'RECEIVED', customer_approval_status text NOT NULL DEFAULT 'PENDING', created_by uuid REFERENCES users(id), created_at timestamptz DEFAULT now(), updated_at timestamptz DEFAULT now(), UNIQUE(organization_id,job_no));
CREATE TABLE IF NOT EXISTS job_stage_history(id uuid PRIMARY KEY DEFAULT gen_random_uuid(), job_card_id uuid REFERENCES job_cards(id), from_status text, to_status text NOT NULL, changed_by uuid REFERENCES users(id), reason text, changed_at timestamptz DEFAULT now());
CREATE TABLE IF NOT EXISTS job_approvals(id uuid PRIMARY KEY DEFAULT gen_random_uuid(), job_card_id uuid REFERENCES job_cards(id), approval_type text NOT NULL, approved_by uuid REFERENCES users(id), approved_at timestamptz DEFAULT now());
CREATE TABLE IF NOT EXISTS parts(id uuid PRIMARY KEY DEFAULT gen_random_uuid(), organization_id uuid REFERENCES organizations(id), sku text NOT NULL, barcode text, name text NOT NULL, category text, min_level numeric NOT NULL DEFAULT 0, max_level numeric NOT NULL DEFAULT 0, average_cost numeric(12,2) NOT NULL DEFAULT 0, is_active boolean DEFAULT true, UNIQUE(organization_id,sku));
CREATE TABLE IF NOT EXISTS stores(id uuid PRIMARY KEY DEFAULT gen_random_uuid(), organization_id uuid REFERENCES organizations(id), code text NOT NULL, name text NOT NULL, UNIQUE(organization_id,code));
CREATE TABLE IF NOT EXISTS stock_balances(id uuid PRIMARY KEY DEFAULT gen_random_uuid(), store_id uuid REFERENCES stores(id), part_id uuid REFERENCES parts(id), on_hand numeric NOT NULL DEFAULT 0, reserved numeric NOT NULL DEFAULT 0, version int NOT NULL DEFAULT 0, UNIQUE(store_id,part_id));
CREATE TABLE IF NOT EXISTS stock_movements(id uuid PRIMARY KEY DEFAULT gen_random_uuid(), organization_id uuid REFERENCES organizations(id), store_id uuid REFERENCES stores(id), part_id uuid REFERENCES parts(id), type text NOT NULL, quantity numeric NOT NULL, reference_type text, reference_id uuid, unit_cost numeric(12,2), reason text, created_by uuid REFERENCES users(id), created_at timestamptz DEFAULT now());
CREATE TABLE IF NOT EXISTS labor_entries(id uuid PRIMARY KEY DEFAULT gen_random_uuid(), job_card_id uuid REFERENCES job_cards(id), technician_id uuid REFERENCES users(id), minutes int NOT NULL CHECK(minutes>0), rate_snapshot numeric(12,2) NOT NULL DEFAULT 0, billable boolean DEFAULT true, note text, created_at timestamptz DEFAULT now());
CREATE TABLE IF NOT EXISTS job_parts(id uuid PRIMARY KEY DEFAULT gen_random_uuid(), job_card_id uuid REFERENCES job_cards(id), part_id uuid REFERENCES parts(id), store_id uuid REFERENCES stores(id), quantity numeric NOT NULL CHECK(quantity>0), unit_cost_snapshot numeric(12,2) NOT NULL, unit_price_snapshot numeric(12,2) NOT NULL, status text NOT NULL DEFAULT 'ISSUED', issued_by uuid REFERENCES users(id), issued_at timestamptz DEFAULT now());
CREATE TABLE IF NOT EXISTS vendors(id uuid PRIMARY KEY DEFAULT gen_random_uuid(), organization_id uuid REFERENCES organizations(id), name text NOT NULL, contact text, status text DEFAULT 'ACTIVE');
CREATE TABLE IF NOT EXISTS purchase_orders(id uuid PRIMARY KEY DEFAULT gen_random_uuid(), organization_id uuid REFERENCES organizations(id), po_no text NOT NULL, vendor_id uuid REFERENCES vendors(id), status text DEFAULT 'DRAFT', total_amount numeric(12,2) DEFAULT 0, created_by uuid REFERENCES users(id), submitted_at timestamptz, UNIQUE(organization_id,po_no));
CREATE TABLE IF NOT EXISTS purchase_order_lines(id uuid PRIMARY KEY DEFAULT gen_random_uuid(), purchase_order_id uuid REFERENCES purchase_orders(id) ON DELETE CASCADE, part_id uuid REFERENCES parts(id), ordered_qty numeric NOT NULL, unit_cost numeric(12,2) NOT NULL, received_qty numeric DEFAULT 0);
CREATE TABLE IF NOT EXISTS purchase_approvals(id uuid PRIMARY KEY DEFAULT gen_random_uuid(), purchase_order_id uuid REFERENCES purchase_orders(id), approval_level int NOT NULL, approved_by uuid REFERENCES users(id), decision text NOT NULL, approved_at timestamptz DEFAULT now());
CREATE TABLE IF NOT EXISTS goods_receipts(id uuid PRIMARY KEY DEFAULT gen_random_uuid(), purchase_order_id uuid REFERENCES purchase_orders(id), store_id uuid REFERENCES stores(id), received_by uuid REFERENCES users(id), status text DEFAULT 'PENDING', accepted_at timestamptz);
CREATE TABLE IF NOT EXISTS goods_receipt_lines(id uuid PRIMARY KEY DEFAULT gen_random_uuid(), goods_receipt_id uuid REFERENCES goods_receipts(id) ON DELETE CASCADE, purchase_order_line_id uuid REFERENCES purchase_order_lines(id), accepted_qty numeric NOT NULL, rejected_qty numeric DEFAULT 0, unit_cost numeric(12,2) NOT NULL);
CREATE TABLE IF NOT EXISTS invoices(id uuid PRIMARY KEY DEFAULT gen_random_uuid(), organization_id uuid REFERENCES organizations(id), invoice_no text NOT NULL, job_card_id uuid REFERENCES job_cards(id), status text DEFAULT 'DRAFT', subtotal_parts numeric(12,2) DEFAULT 0, subtotal_labor numeric(12,2) DEFAULT 0, sublet_cost numeric(12,2) DEFAULT 0, discount_amount numeric(12,2) DEFAULT 0, tax_rate numeric(8,4) DEFAULT 0, tax_amount numeric(12,2) DEFAULT 0, total_amount numeric(12,2) DEFAULT 0, issued_at timestamptz, UNIQUE(organization_id,invoice_no));
CREATE TABLE IF NOT EXISTS invoice_lines(id uuid PRIMARY KEY DEFAULT gen_random_uuid(), invoice_id uuid REFERENCES invoices(id) ON DELETE CASCADE, source_type text, source_id uuid, description text, quantity numeric, unit_price numeric(12,2), line_total numeric(12,2));
CREATE TABLE IF NOT EXISTS payment_references(id uuid PRIMARY KEY DEFAULT gen_random_uuid(), invoice_id uuid REFERENCES invoices(id), reference_no text, amount numeric(12,2), paid_at timestamptz DEFAULT now(), method text, note text);
CREATE TABLE IF NOT EXISTS courses(id uuid PRIMARY KEY DEFAULT gen_random_uuid(), organization_id uuid REFERENCES organizations(id), code text NOT NULL, name text NOT NULL, duration_hours int DEFAULT 0);
CREATE TABLE IF NOT EXISTS training_sessions(id uuid PRIMARY KEY DEFAULT gen_random_uuid(), organization_id uuid REFERENCES organizations(id), course_id uuid REFERENCES courses(id), starts_at timestamptz NOT NULL, ends_at timestamptz NOT NULL, bay_id uuid REFERENCES bays(id), mentor_id uuid REFERENCES users(id), capacity int NOT NULL, status text DEFAULT 'DRAFT');
CREATE TABLE IF NOT EXISTS students(id uuid PRIMARY KEY DEFAULT gen_random_uuid(), organization_id uuid REFERENCES organizations(id), user_id uuid REFERENCES users(id), student_no text NOT NULL, status text DEFAULT 'ACTIVE');
CREATE TABLE IF NOT EXISTS enrollments(id uuid PRIMARY KEY DEFAULT gen_random_uuid(), session_id uuid REFERENCES training_sessions(id), student_id uuid REFERENCES students(id), UNIQUE(session_id,student_id));
CREATE TABLE IF NOT EXISTS practical_tasks(id uuid PRIMARY KEY DEFAULT gen_random_uuid(), course_id uuid REFERENCES courses(id), code text NOT NULL, title text NOT NULL, required boolean DEFAULT true);
CREATE TABLE IF NOT EXISTS attendances(id uuid PRIMARY KEY DEFAULT gen_random_uuid(), session_id uuid REFERENCES training_sessions(id), student_id uuid REFERENCES students(id), status text NOT NULL, recorded_by uuid REFERENCES users(id), UNIQUE(session_id,student_id));
CREATE TABLE IF NOT EXISTS assessments(id uuid PRIMARY KEY DEFAULT gen_random_uuid(), session_id uuid REFERENCES training_sessions(id), student_id uuid REFERENCES students(id), task_id uuid REFERENCES practical_tasks(id), result text NOT NULL, time_on_task int DEFAULT 0, mentor_note text, status text DEFAULT 'PENDING_SIGNATURE', entered_by uuid REFERENCES users(id), UNIQUE(session_id,student_id,task_id));
CREATE TABLE IF NOT EXISTS assessment_signoffs(id uuid PRIMARY KEY DEFAULT gen_random_uuid(), assessment_id uuid REFERENCES assessments(id), signed_by uuid REFERENCES users(id), signed_at timestamptz DEFAULT now());
CREATE TABLE IF NOT EXISTS certificates(id uuid PRIMARY KEY DEFAULT gen_random_uuid(), organization_id uuid REFERENCES organizations(id), student_id uuid REFERENCES students(id), course_id uuid REFERENCES courses(id), public_token_hash text NOT NULL, issue_date timestamptz DEFAULT now(), status text DEFAULT 'ISSUED', revoked_at timestamptz);
CREATE TABLE IF NOT EXISTS audit_events(id uuid PRIMARY KEY DEFAULT gen_random_uuid(), organization_id uuid REFERENCES organizations(id), actor_id uuid REFERENCES users(id), action text NOT NULL, entity_type text, entity_id uuid, request_id text, metadata_json jsonb DEFAULT '{}', occurred_at timestamptz DEFAULT now());
CREATE INDEX IF NOT EXISTS idx_jobs_scope_status ON job_cards(organization_id,status);
CREATE INDEX IF NOT EXISTS idx_stock_movements_part ON stock_movements(store_id,part_id,created_at);
CREATE INDEX IF NOT EXISTS idx_audit_scope_time ON audit_events(organization_id,occurred_at);

-- ============ 002_extend.sql ============
-- 002_extend.sql : closes the gaps found in the Project-6 backend audit.

-- ---------- Organisation level configuration (no more hard-coded thresholds) ----------
CREATE TABLE IF NOT EXISTS org_settings(
  organization_id uuid PRIMARY KEY REFERENCES organizations(id) ON DELETE CASCADE,
  currency text NOT NULL DEFAULT 'EGP',
  tax_rate numeric(8,4) NOT NULL DEFAULT 0.14,
  po_approval_threshold numeric(12,2) NOT NULL DEFAULT 1000,
  po_approvals_required_above int NOT NULL DEFAULT 2,
  po_approvals_required_below int NOT NULL DEFAULT 1,
  reminder_interval_days int NOT NULL DEFAULT 180,
  reminder_interval_km int NOT NULL DEFAULT 10000,
  certificate_min_pass_ratio numeric(5,4) NOT NULL DEFAULT 1.0,
  certificate_min_attendance_ratio numeric(5,4) NOT NULL DEFAULT 0.75
);

-- ---------- Jobs: schedule window (needed for real conflict detection) + approval detail ----------
ALTER TABLE job_cards ADD COLUMN IF NOT EXISTS scheduled_start_at timestamptz;
ALTER TABLE job_cards ADD COLUMN IF NOT EXISTS scheduled_end_at   timestamptz;
ALTER TABLE job_cards ADD COLUMN IF NOT EXISTS estimate_amount numeric(12,2) NOT NULL DEFAULT 0;
ALTER TABLE job_cards ADD COLUMN IF NOT EXISTS closed_at timestamptz;
ALTER TABLE job_approvals ADD COLUMN IF NOT EXISTS decision text NOT NULL DEFAULT 'APPROVED';
ALTER TABLE job_approvals ADD COLUMN IF NOT EXISTS channel text;
ALTER TABLE job_approvals ADD COLUMN IF NOT EXISTS reference_no text;
ALTER TABLE job_approvals ADD COLUMN IF NOT EXISTS approved_amount numeric(12,2);
ALTER TABLE job_approvals ADD COLUMN IF NOT EXISTS note text;

CREATE TABLE IF NOT EXISTS job_sublets(
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  job_card_id uuid NOT NULL REFERENCES job_cards(id) ON DELETE CASCADE,
  vendor_id uuid REFERENCES vendors(id),
  description text NOT NULL,
  cost numeric(12,2) NOT NULL CHECK(cost >= 0),
  price numeric(12,2) NOT NULL CHECK(price >= 0),
  billable boolean NOT NULL DEFAULT true,
  created_by uuid REFERENCES users(id),
  created_at timestamptz NOT NULL DEFAULT now()
);

-- ---------- Inventory: reversal, adjustment, negative-stock hard guard ----------
ALTER TABLE job_parts ADD COLUMN IF NOT EXISTS reversed_qty numeric NOT NULL DEFAULT 0;
ALTER TABLE stock_movements ADD COLUMN IF NOT EXISTS balance_after numeric;

CREATE TABLE IF NOT EXISTS part_reversals(
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  job_part_id uuid NOT NULL REFERENCES job_parts(id),
  quantity numeric NOT NULL CHECK(quantity > 0),
  reason text NOT NULL,
  authorized_by uuid NOT NULL REFERENCES users(id),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS stock_adjustments(
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES organizations(id),
  store_id uuid NOT NULL REFERENCES stores(id),
  part_id uuid NOT NULL REFERENCES parts(id),
  delta numeric NOT NULL,
  reason text NOT NULL,
  approved_by uuid NOT NULL REFERENCES users(id),
  created_at timestamptz NOT NULL DEFAULT now()
);

DO $$ BEGIN
  ALTER TABLE stock_balances ADD CONSTRAINT stock_balances_non_negative CHECK (on_hand >= 0);
EXCEPTION WHEN duplicate_object OR duplicate_table THEN NULL; END $$;

-- ---------- Purchasing: state machine + receipt numbering ----------
ALTER TABLE purchase_orders ADD COLUMN IF NOT EXISTS approvals_required int NOT NULL DEFAULT 1;
ALTER TABLE purchase_orders ADD COLUMN IF NOT EXISTS submitted_by uuid REFERENCES users(id);
ALTER TABLE purchase_orders ADD COLUMN IF NOT EXISTS decided_at timestamptz;
ALTER TABLE purchase_orders ADD COLUMN IF NOT EXISTS reject_reason text;
ALTER TABLE goods_receipts ADD COLUMN IF NOT EXISTS organization_id uuid REFERENCES organizations(id);
ALTER TABLE goods_receipts ADD COLUMN IF NOT EXISTS gr_no text;
ALTER TABLE goods_receipts ADD COLUMN IF NOT EXISTS accepted_by uuid REFERENCES users(id);
ALTER TABLE goods_receipts ADD COLUMN IF NOT EXISTS created_at timestamptz NOT NULL DEFAULT now();

DO $$ BEGIN
  ALTER TABLE purchase_approvals ADD CONSTRAINT purchase_approvals_one_per_user UNIQUE(purchase_order_id, approved_by);
EXCEPTION WHEN duplicate_object OR duplicate_table THEN NULL; END $$;

-- ---------- Invoicing ----------
ALTER TABLE invoices ADD COLUMN IF NOT EXISTS sublet_price numeric(12,2) NOT NULL DEFAULT 0;
ALTER TABLE invoices ADD COLUMN IF NOT EXISTS created_by uuid REFERENCES users(id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_invoice_per_job ON invoices(job_card_id) WHERE status <> 'CANCELLED';

-- ---------- Customers / vehicles: service reminders ----------
CREATE TABLE IF NOT EXISTS service_reminders(
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES organizations(id),
  vehicle_id uuid NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
  job_card_id uuid REFERENCES job_cards(id),
  due_date date NOT NULL,
  due_mileage int,
  reason text NOT NULL,
  status text NOT NULL DEFAULT 'PENDING',
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_reminders_due ON service_reminders(organization_id,status,due_date);

-- ---------- Training depth: terms, groups, competencies ----------
CREATE TABLE IF NOT EXISTS terms(
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES organizations(id),
  code text NOT NULL, name text NOT NULL,
  starts_on date NOT NULL, ends_on date NOT NULL,
  UNIQUE(organization_id, code)
);
ALTER TABLE courses ADD COLUMN IF NOT EXISTS term_id uuid REFERENCES terms(id);
ALTER TABLE training_sessions ADD COLUMN IF NOT EXISTS title text;
ALTER TABLE training_sessions ADD COLUMN IF NOT EXISTS group_id uuid;
ALTER TABLE students ADD COLUMN IF NOT EXISTS full_name text;
ALTER TABLE students ADD COLUMN IF NOT EXISTS group_id uuid;
ALTER TABLE practical_tasks ADD COLUMN IF NOT EXISTS weight numeric NOT NULL DEFAULT 1;

CREATE TABLE IF NOT EXISTS student_groups(
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES organizations(id),
  term_id uuid REFERENCES terms(id),
  code text NOT NULL, name text NOT NULL,
  UNIQUE(organization_id, code)
);

CREATE TABLE IF NOT EXISTS competencies(
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES organizations(id),
  code text NOT NULL, name text NOT NULL,
  UNIQUE(organization_id, code)
);

CREATE TABLE IF NOT EXISTS task_competencies(
  task_id uuid REFERENCES practical_tasks(id) ON DELETE CASCADE,
  competency_id uuid REFERENCES competencies(id) ON DELETE CASCADE,
  PRIMARY KEY(task_id, competency_id)
);

ALTER TABLE certificates ADD COLUMN IF NOT EXISTS issued_by uuid REFERENCES users(id);
ALTER TABLE certificates ADD COLUMN IF NOT EXISTS revoke_reason text;
ALTER TABLE certificates ADD COLUMN IF NOT EXISTS coverage_json jsonb NOT NULL DEFAULT '{}';
CREATE UNIQUE INDEX IF NOT EXISTS uq_certificate_student_course ON certificates(student_id, course_id) WHERE status = 'ISSUED';

-- ---------- Attachments, notifications, prediction runs, login throttling ----------
CREATE TABLE IF NOT EXISTS attachments(
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES organizations(id),
  entity_type text NOT NULL,
  entity_id uuid NOT NULL,
  file_name text NOT NULL,
  content_type text NOT NULL,
  size_bytes bigint NOT NULL CHECK(size_bytes >= 0),
  storage_key text NOT NULL,
  uploaded_by uuid REFERENCES users(id),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_attachments_entity ON attachments(organization_id, entity_type, entity_id);

CREATE TABLE IF NOT EXISTS notifications(
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES organizations(id),
  recipient_id uuid REFERENCES users(id),
  channel text NOT NULL DEFAULT 'IN_APP',
  topic text NOT NULL,
  payload_json jsonb NOT NULL DEFAULT '{}',
  status text NOT NULL DEFAULT 'QUEUED',
  read_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_notifications_recipient ON notifications(recipient_id, status, created_at DESC);

CREATE TABLE IF NOT EXISTS prediction_runs(
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES organizations(id),
  model_key text NOT NULL,
  model_version text NOT NULL,
  strategy text NOT NULL,
  subject_type text NOT NULL,
  subject_id uuid,
  score numeric,
  band text,
  features_json jsonb NOT NULL DEFAULT '{}',
  explanation_json jsonb NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_prediction_subject ON prediction_runs(organization_id, model_key, subject_id, created_at DESC);

CREATE TABLE IF NOT EXISTS login_attempts(
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email text NOT NULL,
  ip text,
  success boolean NOT NULL,
  attempted_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_login_attempts ON login_attempts(email, attempted_at DESC);

ALTER TABLE refresh_tokens ADD COLUMN IF NOT EXISTS replaced_by uuid;
ALTER TABLE refresh_tokens ADD COLUMN IF NOT EXISTS created_at timestamptz NOT NULL DEFAULT now();
CREATE INDEX IF NOT EXISTS idx_refresh_token_hash ON refresh_tokens(token_hash);

-- ---------- Indexes that the dashboards/exports rely on ----------
CREATE INDEX IF NOT EXISTS idx_job_parts_job ON job_parts(job_card_id);
CREATE INDEX IF NOT EXISTS idx_labor_job ON labor_entries(job_card_id);
CREATE INDEX IF NOT EXISTS idx_sessions_window ON training_sessions(organization_id, starts_at, ends_at);
CREATE INDEX IF NOT EXISTS idx_assessments_student ON assessments(student_id, status);


-- ============ 003_doc_counters.sql ============
-- 003: race-free document numbering
CREATE TABLE IF NOT EXISTS doc_counters(
  organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  doc_type text NOT NULL,
  value bigint NOT NULL DEFAULT 0,
  PRIMARY KEY(organization_id, doc_type)
);

-- ============ 004_pdf_gaps.sql ============
-- 004: closes the gaps found when mapping the implementation against the official PDF
-- (WST-FR-02 bilingual data, FR-03 archiving, FR-04 work checklist, FR-06 reservations,
--  FR-07 compatibility + stock counts, FR-14 human override).

-- ---------- WST-FR-02: bilingual reference data kept in the database, identifiers stay LTR ----------
ALTER TABLE parts           ADD COLUMN IF NOT EXISTS name_ar text;
ALTER TABLE courses         ADD COLUMN IF NOT EXISTS name_ar text;
ALTER TABLE practical_tasks ADD COLUMN IF NOT EXISTS title_ar text;
ALTER TABLE bays            ADD COLUMN IF NOT EXISTS name_ar text;
ALTER TABLE competencies    ADD COLUMN IF NOT EXISTS name_ar text;
ALTER TABLE organizations   ADD COLUMN IF NOT EXISTS name_ar text;

-- ---------- WST-FR-03: archiving instead of deletion ----------
ALTER TABLE customers ADD COLUMN IF NOT EXISTS archived_at timestamptz;
ALTER TABLE vehicles  ADD COLUMN IF NOT EXISTS archived_at timestamptz;
ALTER TABLE vehicles  ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now();
ALTER TABLE vehicles  ADD COLUMN IF NOT EXISTS created_at timestamptz NOT NULL DEFAULT now();
ALTER TABLE vehicles  ADD COLUMN IF NOT EXISTS created_by uuid REFERENCES users(id);
ALTER TABLE customers ADD COLUMN IF NOT EXISTS created_by uuid REFERENCES users(id);

-- ---------- WST-FR-04: work checklist on the job card ----------
CREATE TABLE IF NOT EXISTS work_items(
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  job_card_id uuid NOT NULL REFERENCES job_cards(id) ON DELETE CASCADE,
  sequence int NOT NULL DEFAULT 1,
  description text NOT NULL,
  description_ar text,
  status text NOT NULL DEFAULT 'PENDING',
  required boolean NOT NULL DEFAULT true,
  completed_by uuid REFERENCES users(id),
  completed_at timestamptz,
  note text,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_work_items_job ON work_items(job_card_id);

-- ---------- WST-FR-06: reservations before issue ----------
CREATE TABLE IF NOT EXISTS stock_reservations(
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES organizations(id),
  job_card_id uuid NOT NULL REFERENCES job_cards(id) ON DELETE CASCADE,
  store_id uuid NOT NULL REFERENCES stores(id),
  part_id uuid NOT NULL REFERENCES parts(id),
  quantity numeric NOT NULL CHECK(quantity > 0),
  status text NOT NULL DEFAULT 'ACTIVE',
  reserved_by uuid REFERENCES users(id),
  released_reason text,
  created_at timestamptz NOT NULL DEFAULT now(),
  released_at timestamptz
);
CREATE INDEX IF NOT EXISTS idx_reservations_job ON stock_reservations(job_card_id, status);

-- ---------- WST-FR-07: vehicle compatibility and physical stock counts ----------
CREATE TABLE IF NOT EXISTS part_compatibilities(
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  part_id uuid NOT NULL REFERENCES parts(id) ON DELETE CASCADE,
  make text NOT NULL,
  model text,
  year_from int,
  year_to int,
  UNIQUE(part_id, make, model, year_from, year_to)
);

CREATE TABLE IF NOT EXISTS stock_counts(
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES organizations(id),
  store_id uuid NOT NULL REFERENCES stores(id),
  count_no text NOT NULL,
  status text NOT NULL DEFAULT 'OPEN',
  counted_by uuid REFERENCES users(id),
  approved_by uuid REFERENCES users(id),
  reason text,
  created_at timestamptz NOT NULL DEFAULT now(),
  approved_at timestamptz,
  UNIQUE(organization_id, count_no)
);

CREATE TABLE IF NOT EXISTS stock_count_lines(
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  stock_count_id uuid NOT NULL REFERENCES stock_counts(id) ON DELETE CASCADE,
  part_id uuid NOT NULL REFERENCES parts(id),
  system_qty numeric NOT NULL,
  counted_qty numeric NOT NULL CHECK(counted_qty >= 0),
  variance numeric NOT NULL,
  UNIQUE(stock_count_id, part_id)
);

-- ---------- WST-FR-14: human override and evaluation outcome on every suggestion ----------
ALTER TABLE prediction_runs ADD COLUMN IF NOT EXISTS decision text;
ALTER TABLE prediction_runs ADD COLUMN IF NOT EXISTS decided_by uuid REFERENCES users(id);
ALTER TABLE prediction_runs ADD COLUMN IF NOT EXISTS decided_at timestamptz;
ALTER TABLE prediction_runs ADD COLUMN IF NOT EXISTS override_value numeric;
ALTER TABLE prediction_runs ADD COLUMN IF NOT EXISTS decision_note text;
ALTER TABLE prediction_runs ADD COLUMN IF NOT EXISTS outcome_json jsonb NOT NULL DEFAULT '{}';
ALTER TABLE prediction_runs ADD COLUMN IF NOT EXISTS fallback_used boolean NOT NULL DEFAULT true;

-- ---------- Acceptance scenario 1 needs a second store to be usable for transfers ----------
CREATE INDEX IF NOT EXISTS idx_stock_counts_store ON stock_counts(organization_id, store_id, status);

-- ============ 005_hardening.sql ============
-- 005_hardening.sql
-- Closes the security and commercial-rule gaps found in the second audit:
--   * audit_events is immutable at the database level (WST security: "immutable history")
--   * one shared bay calendar with a real exclusion constraint (risk control: "database constraints")
--   * invoice prices come from catalogue data, never from the client (the brief's "hardest part")
--   * attachment storage keys are constrained
--   * goods receipts cannot over-receive even with concurrent pending receipts

CREATE EXTENSION IF NOT EXISTS btree_gist;

-- ---------------------------------------------------------------- immutable audit history
CREATE OR REPLACE FUNCTION audit_events_immutable() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'audit_events is append-only: % is not permitted', TG_OP
    USING ERRCODE = '42501';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_audit_events_no_update ON audit_events;
CREATE TRIGGER trg_audit_events_no_update
  BEFORE UPDATE OR DELETE ON audit_events
  FOR EACH ROW EXECUTE FUNCTION audit_events_immutable();

-- TRUNCATE bypasses row triggers, so it is blocked separately.
DROP TRIGGER IF EXISTS trg_audit_events_no_truncate ON audit_events;
CREATE TRIGGER trg_audit_events_no_truncate
  BEFORE TRUNCATE ON audit_events
  FOR EACH STATEMENT EXECUTE FUNCTION audit_events_immutable();

-- ---------------------------------------------------------------- one shared bay calendar
-- Workshop jobs and training sessions both book the same physical bays. A single table with a
-- GiST exclusion constraint makes a double booking impossible even under concurrent commits,
-- in either direction, which application-level checks alone cannot guarantee.
CREATE TABLE IF NOT EXISTS bay_reservations(
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  bay_id uuid NOT NULL REFERENCES bays(id) ON DELETE CASCADE,
  source_type text NOT NULL CHECK (source_type IN ('JOB', 'SESSION')),
  source_id uuid NOT NULL,
  during tstzrange NOT NULL,
  created_by uuid REFERENCES users(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (source_type, source_id)
);

DO $$ BEGIN
  ALTER TABLE bay_reservations
    ADD CONSTRAINT bay_reservations_no_overlap
    EXCLUDE USING gist (bay_id WITH =, during WITH &&);
EXCEPTION WHEN duplicate_object OR duplicate_table THEN NULL; END $$;

CREATE INDEX IF NOT EXISTS idx_bay_reservations_bay ON bay_reservations(bay_id, during);

-- ---------------------------------------------------------------- prices come from the catalogue
ALTER TABLE parts ADD COLUMN IF NOT EXISTS sell_price numeric(12,2) NOT NULL DEFAULT 0;
DO $$ BEGIN
  ALTER TABLE parts ADD CONSTRAINT parts_sell_price_non_negative CHECK (sell_price >= 0);
EXCEPTION WHEN duplicate_object OR duplicate_table THEN NULL; END $$;

-- Parts seeded before this migration get a default retail margin so no priced row is left at 0.
UPDATE parts SET sell_price = ROUND(average_cost * 1.35, 2) WHERE sell_price = 0 AND average_cost > 0;

ALTER TABLE org_settings ADD COLUMN IF NOT EXISTS default_labor_rate numeric(12,2) NOT NULL DEFAULT 150;
ALTER TABLE org_settings ADD COLUMN IF NOT EXISTS max_export_rows int NOT NULL DEFAULT 5000;
ALTER TABLE users        ADD COLUMN IF NOT EXISTS labor_rate numeric(12,2);

-- Per service-type labour rates; the technician override and the org default are the fallbacks.
CREATE TABLE IF NOT EXISTS labor_rates(
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  service_type text NOT NULL,
  rate numeric(12,2) NOT NULL CHECK (rate >= 0),
  effective_from date NOT NULL DEFAULT current_date,
  UNIQUE(organization_id, service_type)
);

-- Which source each stored price came from, so an invoice can prove it was not typed in.
ALTER TABLE job_parts     ADD COLUMN IF NOT EXISTS price_source text NOT NULL DEFAULT 'PART_SELL_PRICE';
ALTER TABLE labor_entries ADD COLUMN IF NOT EXISTS rate_source  text NOT NULL DEFAULT 'ORG_DEFAULT';

-- ---------------------------------------------------------------- attachments
ALTER TABLE attachments ADD COLUMN IF NOT EXISTS scan_status text NOT NULL DEFAULT 'PENDING';
DO $$ BEGIN
  ALTER TABLE attachments ADD CONSTRAINT attachments_storage_key_safe
    CHECK (storage_key ~ '^[A-Za-z0-9][A-Za-z0-9._/-]{0,255}$' AND storage_key NOT LIKE '%..%');
EXCEPTION WHEN duplicate_object OR duplicate_table THEN NULL; END $$;

-- ---------------------------------------------------------------- certificates: re-renderable QR
-- The raw verification token was previously only returned once, so a student could never get their
-- QR code again. It is now kept encrypted (AES-256-GCM) and only decryptable by the API.
ALTER TABLE certificates ADD COLUMN IF NOT EXISTS token_cipher text;

-- ---------------------------------------------------------------- goods receipts
CREATE INDEX IF NOT EXISTS idx_gr_lines_po_line ON goods_receipt_lines(purchase_order_line_id);
CREATE INDEX IF NOT EXISTS idx_goods_receipts_po ON goods_receipts(purchase_order_id, status);

-- ---------------------------------------------------------------- customers / vehicles
ALTER TABLE customers ADD COLUMN IF NOT EXISTS notes text;
