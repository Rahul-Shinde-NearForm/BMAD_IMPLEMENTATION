# Sprint 1 Billing Implementation Checklist

Date: 2026-05-02
Sprint Goal: Deliver OPD billing foundation with mandatory/optional consultation fee handling and consolidated invoice generation.
Story Scope: BM-1.1, BM-1.2, BM-1.3, BM-1.4

## 1) Story-to-Task Mapping

### BM-1.1 Create OPD Billing Ledger on Visit Start

Backend Tasks:
- Create model `BillingLedger` linked to `opd_number` with unique constraint.
- Add fields: `patient`, `doctor`, `visit_date`, `status`, `created_by`, `updated_by`, timestamps.
- Add service method: `create_or_get_active_ledger(opd_number, patient_id, doctor_id, visit_date, actor)`.
- Add API endpoint: `GET/POST /api/billing/ledger/by-opd/`.
- Ensure idempotent behavior on repeated requests.

Frontend Tasks:
- Add ledger summary card to receptionist workflow with status badge.
- On patient selection or appointment open, call ledger fetch/create endpoint.
- Show ledger ID and OPD number in header area.

Validation Tasks:
- Reject missing or invalid `opd_number`.
- Return existing ledger when active ledger already exists.

### BM-1.2 Capture Mandatory New OPD Fee

Backend Tasks:
- Create model `BillingLineItem` for fee entries.
- Add line-item type enum with `OPD_NEW_FEE`.
- Add validation rule: new visit cannot finalize without at least one `OPD_NEW_FEE` line.
- Add API endpoint to add consultation fee line to ledger.
- Integrate validation in finalize endpoint.

Frontend Tasks:
- Add mandatory new-fee section in billing panel.
- Provide amount input and add-to-ledger action.
- On finalize attempt, display blocking error if fee missing.

Validation Tasks:
- Enforce positive amount.
- Prevent duplicate mandatory fee line unless override is explicitly allowed by policy.

### BM-1.3 Capture Optional Repeat OPD Fee

Backend Tasks:
- Add repeat fee decision fields to ledger: `repeat_fee_decision` and `repeat_fee_reason`.
- Enforce reason required when decision is `NO`.
- If decision is `YES`, create `OPD_REPEAT_FEE` line item.
- Add audit log entry for decision changes.

Frontend Tasks:
- Add repeat visit toggle: `Charge Repeat Fee? Yes/No`.
- Add conditional reason field when No is selected.
- Persist decision before finalization and show summary in ledger panel.

Validation Tasks:
- Block save when No selected and reason empty.
- Track actor and timestamp for decision changes.

### BM-1.4 Generate Consolidated Invoice

Backend Tasks:
- Create model `Invoice` with immutable `bill_number` after finalization.
- Add total calculator service (subtotal, discount, tax, final total).
- Add finalize endpoint: lock ledger, generate invoice, set immutable state.
- Add invoice view endpoint for print and retrieval.

Frontend Tasks:
- Add invoice preview panel in billing workspace.
- Add finalize action with confirmation.
- Add print invoice button after successful finalization.

Validation Tasks:
- Prevent finalization on already-locked ledger.
- Prevent edits to line items post finalization.

## 2) Database Migration Checklist

- Create migration for `BillingLedger`.
- Create migration for `BillingLineItem`.
- Create migration for `Invoice`.
- Add DB indexes:
  - `BillingLedger.opd_number`
  - `BillingLedger.status`
  - `BillingLineItem.ledger_id`
  - `Invoice.bill_number` (unique)
- Verify migration on local and staging DB snapshots.

## 3) API Contract Checklist

Endpoints to Implement:
- `GET /api/billing/ledger/by-opd/?opd_number=<value>`
- `POST /api/billing/ledger/by-opd/`
- `POST /api/billing/ledger/<ledger_id>/line-items/`
- `POST /api/billing/ledger/<ledger_id>/repeat-fee-decision/`
- `POST /api/billing/ledger/<ledger_id>/finalize/`
- `GET /api/billing/invoice/<invoice_id>/`

Request/Response Standards:
- Standardize success payload: `status`, `data`, `message`.
- Standardize validation error payload for frontend rendering.
- Include actor and timestamp metadata in audit-sensitive responses.

## 4) UI Implementation Checklist

Reception Billing Workspace:
- Add ledger header section (OPD number, patient name, status).
- Add fee section for new/repeat fee capture.
- Add line-item table and totals block.
- Add finalize + print controls.
- Preserve mobile-responsive behavior for tablet front-desk usage.

State Handling:
- Disable finalize while fee validations fail.
- Show inline field errors and top-level action errors.
- Refresh totals and status after each successful line mutation.

## 5) Test Plan Checklist

Unit Tests:
- Ledger idempotent create-or-get by OPD number.
- Mandatory fee validation for new visit.
- Repeat fee reason required when decision No.
- Invoice total calculation correctness.
- Ledger lock behavior after finalize.

Integration Tests:
- Full flow: create ledger -> add fee -> finalize -> fetch invoice.
- Duplicate ledger creation attempts return same active ledger.
- Finalize fails when mandatory fee absent.
- Post-finalize line-item mutation is blocked.

E2E Tests:
- Receptionist creates new visit bill and prints invoice.
- Repeat visit with No-fee + reason finalizes successfully.
- Page refresh or revisit preserves active ledger state.

## 6) Definition of Done (Sprint 1)

- BM-1.1 to BM-1.4 acceptance criteria pass.
- Migrations applied cleanly in dev and staging.
- All new APIs documented and consumed in UI.
- Critical unit + integration + E2E tests green.
- Role checks and audit logging active for billing mutations.
- Demo scenario completed by receptionist workflow owner.

## 7) Suggested Execution Sequence (5 Working Days)

Day 1:
- Implement data models and migrations.
- Build ledger create-or-get service and endpoint.

Day 2:
- Implement line-item API and mandatory fee validations.
- Add repeat fee decision API and audit logging.

Day 3:
- Implement finalize and invoice generation endpoints.
- Build invoice retrieval/print API.

Day 4:
- Implement frontend billing workspace updates.
- Connect APIs and add error states.

Day 5:
- Run integration and E2E regression tests.
- Fix defects and complete sprint demo checklist.
