# Billing Module Story Cards

Date: 2026-05-02
Source Backlog: billing-module-epics-stories-2026-05-02.md
Target Product Scope: OPD billing workflow for India tier-2 solo and small multi-doctor clinics

## Story Card Format

Each story card includes:
- Story ID and title
- User story
- Acceptance criteria
- Dependencies
- API and UI notes
- Test checklist
- Definition of done

---

## Epic 1: OPD Ledger and Core Billing Foundation

### Story BM-1.1: Create OPD Billing Ledger on Visit Start

User Story:
As a receptionist, I want each visit to auto-create a billing ledger linked to OPD number, so all charges stay in one record.

Acceptance Criteria:
- On appointment booking or walk-in start, system creates a unique OPD-linked billing ledger.
- Reopening same OPD visit does not create duplicate ledger.
- Ledger includes patient_id, doctor_id, visit_date, status.

Dependencies:
- Existing OPD number generation and appointment entities.

API and UI Notes:
- Add endpoint to create or fetch active ledger by opd_number.
- UI should show ledger header with status badge.

Test Checklist:
- Unit: idempotent ledger creation by opd_number.
- Integration: same request twice returns same ledger.
- E2E: receptionist opens visit and sees active ledger.

Definition of Done:
- Ledger is created and reused correctly across refresh and reopen.

### Story BM-1.2: Capture Mandatory New OPD Fee

User Story:
As a receptionist, I want mandatory OPD fee capture for new visits, so consultation billing is not missed.

Acceptance Criteria:
- New visit requires OPD fee line before checkout.
- Fee line includes amount, timestamp, actor.
- Finalize action blocked if mandatory fee missing.

Dependencies:
- BM-1.1

API and UI Notes:
- Add validation rule for mandatory fee on new visits.
- Show clear blocking message with add-fee action.

Test Checklist:
- Unit: validation fails when fee absent.
- Integration: finalize endpoint returns validation error.
- E2E: receptionist cannot finalize without fee.

Definition of Done:
- Mandatory fee enforcement works end-to-end.

### Story BM-1.3: Capture Optional Repeat OPD Fee

User Story:
As a receptionist, I want optional repeat OPD fee toggle, so clinic policy can be applied flexibly.

Acceptance Criteria:
- Repeat visit shows Yes or No fee toggle.
- If No, reason is mandatory.
- If Yes, fee line added to ledger.
- Toggle and reason are audit logged.

Dependencies:
- BM-1.1

API and UI Notes:
- Add repeat_fee_decision and repeat_fee_reason fields.
- Show compact toggle in ledger panel.

Test Checklist:
- Unit: reason required when No selected.
- Integration: decision persists and logs actor.
- E2E: receptionist sets No with reason and finalizes.

Definition of Done:
- Repeat-visit fee policy is configurable per visit and traceable.

### Story BM-1.4: Generate Consolidated Invoice

User Story:
As a receptionist, I want one consolidated invoice, so patient checkout is clear and fast.

Acceptance Criteria:
- Invoice includes all ledger lines and totals.
- Invoice has immutable bill number after finalization.
- Invoice supports print and view.

Dependencies:
- BM-1.1, BM-1.2, BM-1.3

API and UI Notes:
- Add finalize endpoint to lock ledger and generate invoice number.
- Add invoice view endpoint for display and print.

Test Checklist:
- Unit: total calculator with tax and discount.
- Integration: finalized invoice becomes immutable.
- E2E: receptionist finalizes and prints.

Definition of Done:
- Consolidated billing works reliably for checkout.

---

## Epic 2: Clinical Order to Billing Handoff

### Story BM-2.1: Pull In-House Lab and Radiology Orders into Billing Queue

User Story:
As a receptionist, I want doctor orders in billing queue, so I can add charges accurately.

Acceptance Criteria:
- In-house lab and radiology orders appear as pending billable items.
- Items are tied to OPD number and consultation.
- Status lifecycle is visible: ordered, billed, canceled, completed.

Dependencies:
- Doctor consultation and medical order module.

API and UI Notes:
- Add endpoint: list pending billable orders by patient/opd.
- UI section: pending orders with add-to-bill action.

Test Checklist:
- Unit: in-house filter works correctly.
- Integration: orders map correctly to OPD visit.
- E2E: receptionist adds pending order to bill.

Definition of Done:
- Handoff from consultation to billing is accurate and timely.

### Story BM-2.2: Add Orders to Ledger with Duplicate Prevention

User Story:
As a receptionist, I want duplicate protection while adding order charges, so billing stays accurate.

Acceptance Criteria:
- Same order cannot be billed twice by default.
- Override allowed only for authorized role with reason.
- Source order id is retained for each billed line.

Dependencies:
- BM-2.1

API and UI Notes:
- Duplicate-check service before line insertion.
- Override dialog with reason and role check.

Test Checklist:
- Unit: duplicate detector catches same source order.
- Integration: unauthorized override is denied.
- E2E: duplicate add shows warning.

Definition of Done:
- Duplicate and accidental repeat billing are controlled.

### Story BM-2.3: Pending-Charge Checklist Before Finalization

User Story:
As a receptionist, I want pending checklist before final bill, so no valid order is left unbilled.

Acceptance Criteria:
- Finalization screen shows pending and billed order counts.
- Warning appears if pending in-house orders remain.
- User confirmation required to finalize with pending items.

Dependencies:
- BM-2.1, BM-2.2

API and UI Notes:
- Add pre-finalization summary endpoint.
- Display checklist modal before finalize call.

Test Checklist:
- Unit: pending count logic.
- Integration: finalize requires confirmation flag.
- E2E: pending warning flow works.

Definition of Done:
- Finalization is safe against missed billable services.

---

## Epic 3: Optional In-House Pharmacy Billing Extension

### Story BM-3.1: Enable Pharmacy Module via Clinic Setting

User Story:
As an admin, I want pharmacy billing configurable, so clinics can enable only if required.

Acceptance Criteria:
- Config flag controls pharmacy billing visibility.
- Disabled clinics cannot add pharmacy lines.
- Enabled clinics can access pharmacy billing actions.

Dependencies:
- Existing clinic or tenant settings mechanism.

API and UI Notes:
- Add pharmacy_billing_enabled flag in clinic settings.
- UI hides or shows pharmacy section accordingly.

Test Checklist:
- Unit: feature flag resolver.
- Integration: disabled flag blocks pharmacy endpoints.
- E2E: toggle setting changes billing UI behavior.

Definition of Done:
- Pharmacy billing is optional and safely gated.

### Story BM-3.2: Add Prescription-Linked Pharmacy Lines

User Story:
As a pharmacy or receptionist user, I want prescription-linked medicine charges, so billing follows prescribed treatment.

Acceptance Criteria:
- Prescription items can be imported to billing lines.
- Quantity and rate editable by authorized role.
- Pharmacy lines included in consolidated invoice totals.

Dependencies:
- BM-3.1, prescription module

API and UI Notes:
- Add endpoint: fetch prescription meds by consultation/opd.
- Add grid for medicine charge entry.

Test Checklist:
- Unit: line total calculations.
- Integration: imported lines map to prescription item ids.
- E2E: user adds medicine lines and finalizes.

Definition of Done:
- Pharmacy add-on charges integrate cleanly with OPD billing.

### Story BM-3.3: Handle Non-Stock or Unavailable Items

User Story:
As a pharmacy or receptionist user, I want unavailable items flagged, so billing and fulfillment remain transparent.

Acceptance Criteria:
- Out-of-stock items are clearly marked.
- User can substitute, remove, or mark external purchase.
- Selected resolution appears in invoice notes.

Dependencies:
- BM-3.2 and inventory availability data

API and UI Notes:
- Add stock status field per medicine line.
- Add resolution action for unavailable items.

Test Checklist:
- Unit: unavailable-item state transitions.
- Integration: resolution persists to invoice notes.
- E2E: unavailable flow appears correctly.

Definition of Done:
- Pharmacy edge cases handled without checkout breakdown.

---

## Epic 4: Payments, Controls, and Day-End Reliability

### Story BM-4.1: Mixed Payment Collection and Settlement

User Story:
As a receptionist, I want UPI, cash, card, and split payments, so patients can pay in preferred mode.

Acceptance Criteria:
- Supports UPI, cash, card, and split mode.
- Digital mode captures transaction reference.
- Bill status updates: paid, partially paid, due.

Dependencies:
- BM-1.4

API and UI Notes:
- Payment posting endpoint with mode-wise allocations.
- UI payment panel with split allocation inputs.

Test Checklist:
- Unit: settlement amount validator.
- Integration: partial payment state update.
- E2E: split payment closes bill correctly.

Definition of Done:
- Payment capture supports real front-desk scenarios.

### Story BM-4.2: Payment Failure and Retry Handling

User Story:
As a receptionist, I want safe retry for failed digital payments, so I can close bills confidently.

Acceptance Criteria:
- Failed digital attempt marked non-final.
- Retry can be executed without duplicate paid entries.
- Attempt history is audit logged.

Dependencies:
- BM-4.1

API and UI Notes:
- Add payment attempt log model and retry endpoint.
- UI shows latest attempt state and retry button.

Test Checklist:
- Unit: retry idempotency checks.
- Integration: failed then successful retry updates status.
- E2E: failure and retry flow behaves correctly.

Definition of Done:
- Payment failure handling is resilient and traceable.

### Story BM-4.3: Controlled Amendments, Cancel, Refund, Reprint

User Story:
As authorized staff, I want controlled post-billing actions, so corrections are possible with full audit integrity.

Acceptance Criteria:
- Actions are role-gated.
- Each action requires reason and records actor/time.
- Original invoice snapshot remains preserved.

Dependencies:
- BM-1.4, BM-4.1

API and UI Notes:
- Separate endpoints for amend, cancel, refund, reprint.
- Add audit trail explorer section for bill actions.

Test Checklist:
- Unit: role checks for sensitive actions.
- Integration: refund and cancel update ledger statuses correctly.
- E2E: authorized and unauthorized paths verified.

Definition of Done:
- Post-final actions are secure, controlled, and auditable.

### Story BM-4.4: Day-End Reconciliation Dashboard

User Story:
As receptionist or admin, I want day-end reconciliation, so collections and leakage are visible.

Acceptance Criteria:
- Date-wise and user-wise summary available.
- Payment-mode split totals visible.
- Ordered-vs-billed diagnostics variance report available.

Dependencies:
- BM-4.1, BM-4.2, BM-4.3

API and UI Notes:
- Add day-end summary API.
- UI table with export action and filter controls.

Test Checklist:
- Unit: aggregation logic.
- Integration: totals reconcile with ledger records.
- E2E: day-end report renders for selected date.

Definition of Done:
- Day-end closure and monitoring are operationally usable.

---

## Epic 5: Reception UX, Training, and Adoption Readiness

### Story BM-5.1: One-Screen Reception Billing Workspace

User Story:
As a receptionist, I want one-page billing flow, so checkout is faster and less error-prone.

Acceptance Criteria:
- Single workspace supports patient lookup, ledger, pending orders, payments, finalize.
- Keyboard-friendly interactions for high throughput.
- Common-case flow can complete without page navigation.

Dependencies:
- Core stories from Epics 1, 2, and 4

API and UI Notes:
- Consolidate existing APIs into one workspace screen model.
- Use clear status and action hierarchy.

Test Checklist:
- E2E: full checkout flow in one screen.
- Usability: reduced clicks vs previous workflow baseline.

Definition of Done:
- Front-desk completes standard billing on one screen.

### Story BM-5.2: Role-Based SOP and Guided Tooltips

User Story:
As a new front-desk user, I want guidance in-context, so I can execute billing correctly with minimal training.

Acceptance Criteria:
- Tooltips or helper text for critical steps.
- Warnings for irreversible actions.
- Quick SOP access from billing workspace.

Dependencies:
- BM-5.1

API and UI Notes:
- Static help content with optional role-based variants.
- Maintain concise language for fast reading.

Test Checklist:
- UI: helper content appears in intended steps.
- E2E: new user scenario passes with guidance.

Definition of Done:
- Onboarding friction is visibly reduced.

### Story BM-5.3: Go-Live Monitoring Metrics

User Story:
As product and operations stakeholders, I want adoption and quality metrics, so we can improve quickly post go-live.

Acceptance Criteria:
- Tracks checkout time, amendment rate, failed payment rate, pending-charge override rate.
- Daily trend view for first 30 and 90 days.
- Alert thresholds for abnormal variance.

Dependencies:
- BM-4.4

API and UI Notes:
- Add metrics aggregation job and dashboard endpoint.
- Show trend lines and threshold badges.

Test Checklist:
- Unit: metric calculations.
- Integration: daily rollups generated correctly.
- E2E: dashboard displays current and historical metrics.

Definition of Done:
- Post-launch improvement loop has measurable data.

---

## Sprint Mapping

### Sprint 1
- BM-1.1
- BM-1.2
- BM-1.3
- BM-1.4

### Sprint 2
- BM-2.1
- BM-2.2
- BM-2.3
- BM-4.1

### Sprint 3
- BM-4.2
- BM-4.3
- BM-4.4
- BM-5.1

### Sprint 4
- BM-3.1
- BM-3.2
- BM-3.3
- BM-5.2
- BM-5.3
