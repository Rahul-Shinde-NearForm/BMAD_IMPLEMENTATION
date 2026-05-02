# Sprint 1 Developer Tickets (Ready to Assign)

Date: 2026-05-02
Sprint: Billing Foundation Sprint 1
Story Coverage: BM-1.1, BM-1.2, BM-1.3, BM-1.4

Status Legend:
- To Do
- In Progress
- Blocked
- In Review
- Done

## Team Role Placeholders

- BE-1: Backend Engineer
- FE-1: Frontend Engineer
- QA-1: QA Engineer
- TL-1: Tech Lead

## Ticket Board

| Ticket ID | Story ID | Title | Owner | Estimate (SP) | Dependencies | Status |
|---|---|---|---|---:|---|---|
| S1-BILL-001 | BM-1.1 | Create BillingLedger model with unique OPD mapping | BE-1 | 3 | None | To Do |
| S1-BILL-002 | BM-1.1 | Implement create-or-get ledger service (idempotent) | BE-1 | 3 | S1-BILL-001 | To Do |
| S1-BILL-003 | BM-1.1 | Build ledger by OPD API (GET/POST) | BE-1 | 2 | S1-BILL-002 | To Do |
| S1-BILL-004 | BM-1.1 | Add ledger summary UI block in reception billing workspace | FE-1 | 3 | S1-BILL-003 | To Do |
| S1-BILL-005 | BM-1.2 | Create BillingLineItem model and fee line-type enums | BE-1 | 3 | S1-BILL-001 | To Do |
| S1-BILL-006 | BM-1.2 | Add mandatory new-visit OPD fee validation in finalize flow | BE-1 | 3 | S1-BILL-005 | To Do |
| S1-BILL-007 | BM-1.2 | Add new OPD fee capture UI and blocking validation UX | FE-1 | 3 | S1-BILL-006 | To Do |
| S1-BILL-008 | BM-1.3 | Add repeat-fee decision API with reason validation and audit log | BE-1 | 3 | S1-BILL-005 | To Do |
| S1-BILL-009 | BM-1.3 | Implement repeat fee Yes/No toggle + conditional reason input | FE-1 | 2 | S1-BILL-008 | To Do |
| S1-BILL-010 | BM-1.4 | Create Invoice model and bill number generation service | BE-1 | 5 | S1-BILL-005, S1-BILL-006 | To Do |
| S1-BILL-011 | BM-1.4 | Implement finalize endpoint to lock ledger and generate invoice | BE-1 | 5 | S1-BILL-010 | To Do |
| S1-BILL-012 | BM-1.4 | Build invoice view/print endpoint | BE-1 | 2 | S1-BILL-011 | To Do |
| S1-BILL-013 | BM-1.4 | Add invoice preview, finalize CTA, and print action in UI | FE-1 | 3 | S1-BILL-011, S1-BILL-012 | To Do |
| S1-BILL-014 | BM-1.x | Add and verify DB migrations and indexes in dev/staging | BE-1 | 2 | S1-BILL-001, S1-BILL-005, S1-BILL-010 | To Do |
| S1-BILL-015 | BM-1.x | Implement backend unit tests for ledger, fees, invoice rules | QA-1 | 3 | S1-BILL-011 | To Do |
| S1-BILL-016 | BM-1.x | Implement integration tests for end-to-end API flow | QA-1 | 3 | S1-BILL-011, S1-BILL-012 | To Do |
| S1-BILL-017 | BM-1.x | Implement E2E receptionist flow test for create-finalize-print | QA-1 | 3 | S1-BILL-013 | To Do |
| S1-BILL-018 | BM-1.x | Sprint demo script + UAT signoff checklist preparation | TL-1 | 2 | S1-BILL-015, S1-BILL-016, S1-BILL-017 | To Do |

## Ticket Details

### S1-BILL-001
- Objective: Create `BillingLedger` with OPD uniqueness and base metadata.
- Deliverables:
  - Model fields: opd_number, patient, doctor, visit_date, status, created_by, updated_by, timestamps.
  - Unique DB constraint on opd_number for active ledger semantics.
- Acceptance:
  - Migration succeeds.
  - Duplicate active ledger creation prevented.

### S1-BILL-002
- Objective: Ensure idempotent ledger creation by OPD number.
- Deliverables:
  - `create_or_get_active_ledger` service.
  - Race-safe behavior under repeated calls.
- Acceptance:
  - Repeated create request returns same ledger instance.

### S1-BILL-003
- Objective: Expose ledger retrieval and creation API.
- Deliverables:
  - GET and POST support for by-OPD endpoint.
  - Standard response shape with status, message, data.
- Acceptance:
  - Missing OPD returns validation error.
  - Valid OPD returns ledger data.

### S1-BILL-004
- Objective: Surface ledger context in front-desk UI.
- Deliverables:
  - Ledger card with OPD number, status badge, ledger id.
  - API integration on patient open.
- Acceptance:
  - Ledger card updates on visit change and refresh.

### S1-BILL-005
- Objective: Enable fee line item storage.
- Deliverables:
  - `BillingLineItem` with amount, type, source metadata.
  - Enums for `OPD_NEW_FEE` and `OPD_REPEAT_FEE`.
- Acceptance:
  - Fee lines persist and attach to ledger correctly.

### S1-BILL-006
- Objective: Enforce mandatory new OPD fee.
- Deliverables:
  - Finalize validator requiring at least one new OPD fee line for new visits.
- Acceptance:
  - Finalize blocked when mandatory fee missing.

### S1-BILL-007
- Objective: Add mandatory fee UX controls.
- Deliverables:
  - Amount input and add-fee action.
  - Blocking message on finalize without required fee.
- Acceptance:
  - User cannot proceed unless required fee is captured.

### S1-BILL-008
- Objective: Persist repeat fee policy decisions.
- Deliverables:
  - Repeat fee decision endpoint.
  - Reason validation for No decision.
  - Audit entries with actor and timestamp.
- Acceptance:
  - No decision without reason is rejected.

### S1-BILL-009
- Objective: Implement repeat fee toggle UX.
- Deliverables:
  - Yes/No control.
  - Conditional reason input when No.
- Acceptance:
  - UI prevents save with missing reason when No selected.

### S1-BILL-010
- Objective: Establish invoice domain model.
- Deliverables:
  - `Invoice` model with immutable bill number post-finalization.
  - Total computation service.
- Acceptance:
  - Invoice totals match ledger line sums and tax/discount rules.

### S1-BILL-011
- Objective: Finalize billing safely.
- Deliverables:
  - Endpoint to lock ledger and generate invoice.
  - Write protection for post-finalization edits.
- Acceptance:
  - Finalized ledger cannot be changed.

### S1-BILL-012
- Objective: Support invoice retrieval and print integration.
- Deliverables:
  - Invoice GET endpoint payload optimized for print view.
- Acceptance:
  - Frontend can render printable invoice from endpoint.

### S1-BILL-013
- Objective: Complete finalize and print UI flow.
- Deliverables:
  - Invoice preview panel.
  - Finalize confirmation.
  - Print button after finalization success.
- Acceptance:
  - Reception user can complete end-to-end flow in one workspace.

### S1-BILL-014
- Objective: Ensure migrations and indexing readiness.
- Deliverables:
  - Migration scripts and DB index verification.
- Acceptance:
  - Migration runs cleanly in dev and staging.

### S1-BILL-015
- Objective: Unit-test core business rules.
- Deliverables:
  - Tests for idempotent ledger, fee rules, invoice lock and totals.
- Acceptance:
  - All unit tests pass in CI/local.

### S1-BILL-016
- Objective: Validate service integration paths.
- Deliverables:
  - Integration tests for create -> add fees -> finalize -> fetch invoice.
- Acceptance:
  - Endpoints pass integration suite with realistic fixtures.

### S1-BILL-017
- Objective: Validate receptionist behavior end-to-end.
- Deliverables:
  - E2E test for new visit and repeat visit (No-fee reason path included).
- Acceptance:
  - E2E suite passes with stable selectors.

### S1-BILL-018
- Objective: Prepare closure artifacts for sprint demo/UAT.
- Deliverables:
  - Demo script covering BM-1.1 to BM-1.4.
  - UAT checklist and signoff record template.
- Acceptance:
  - Business owner can run demo and mark acceptance.

## Sprint Capacity Snapshot

- Total Story Points: 53 SP
- Suggested split:
  - BE-1: 26 SP
  - FE-1: 11 SP
  - QA-1: 9 SP
  - TL-1: 2 SP
  - Buffer: 5 SP (defect fixes and dependency slippage)

## Recommended Start Sequence

1. Start S1-BILL-001, S1-BILL-005 in parallel.
2. Start S1-BILL-002 and S1-BILL-003 once ledger model is merged.
3. Start S1-BILL-010 as soon as fee model is stable.
4. FE starts S1-BILL-004 and S1-BILL-007 after API contracts freeze.
5. QA starts S1-BILL-015 once S1-BILL-011 reaches in-review.
