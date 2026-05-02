# OPD Billing Module - Sprint-Ready Epics and Stories

Date: 2026-05-02
Owner: Rahul
Scope: India tier-2, solo and small multi-doctor clinics, receptionist-led billing flow

## Goal

Deliver a receptionist-first billing module where each visit is managed through one OPD-number-linked ledger that supports:
- New patient OPD fee collection
- Optional repeat-visit OPD fee collection
- In-house lab/radiology charge additions after consultation
- Optional in-house pharmacy charge additions
- Final consolidated bill generation and settlement

## Delivery Principles

- Optimize for front-desk speed and low training effort
- Prevent missed and duplicate charges by default
- Keep edits auditable and permission-controlled
- Support mixed payments (UPI, cash, card, split)
- Ship in phases with measurable outcomes

## Epic 1: OPD Ledger and Core Billing Foundation

Objective: Create the OPD-number-centric billing backbone for registration, staged charges, and final invoice.

### Story 1.1: Create OPD Billing Ledger on Visit Start

As a receptionist, I want each visit to auto-create a billing ledger linked to OPD number, so all charges remain in one record.

Acceptance Criteria:
- Given a new appointment or walk-in, when visit starts, then a unique OPD-linked billing ledger is created.
- Given an existing ledger for an OPD number, when reloaded, then no duplicate ledger is created.
- Ledger stores patient, doctor, visit date, and status (open, finalized, amended).

### Story 1.2: Capture Mandatory New OPD Fee

As a receptionist, I want mandatory OPD fee capture for first-time registration, so consultation billing is not missed.

Acceptance Criteria:
- Given a new visit, when registration is completed, then OPD fee prompt is mandatory before billing continuation.
- OPD fee line appears in ledger with timestamp and actor.
- Finalization is blocked if required OPD fee is missing.

### Story 1.3: Capture Optional Repeat OPD Fee

As a receptionist, I want an optional repeat-visit OPD fee toggle, so clinic policy can be applied flexibly.

Acceptance Criteria:
- Repeat visit shows Yes or No toggle for OPD fee.
- If No selected, reason note is captured.
- If Yes selected, charge line is added to ledger.
- Toggle action is audit logged with actor and timestamp.

### Story 1.4: Generate Consolidated Invoice

As a receptionist, I want one consolidated invoice for all OPD-linked charges, so patient checkout is clear and fast.

Acceptance Criteria:
- Invoice includes consultation, diagnostics, radiology, optional pharmacy, discounts, and payment summary.
- Invoice can be printed and reopened for view.
- Once finalized, invoice has immutable bill number.

## Epic 2: Clinical Order to Billing Handoff

Objective: Ensure doctor-ordered in-house services flow safely into billing without missed or duplicate charge risk.

### Story 2.1: Pull In-House Lab and Radiology Orders into Billing Queue

As a receptionist, I want doctor orders to appear in a billing queue, so I can add charges accurately.

Acceptance Criteria:
- In-house lab and radiology orders appear as pending billable items by OPD number.
- Each order shows status: ordered, billed, canceled, completed.
- Non-in-house orders are not shown as billable by default.

### Story 2.2: Add Orders to Ledger with Duplicate Prevention

As a receptionist, I want duplicate protection while adding order charges, so billing remains accurate.

Acceptance Criteria:
- Adding same order twice is blocked unless override permission exists.
- Override requires reason and is audit logged.
- Added lines map back to source consultation order ID.

### Story 2.3: Pending-Charge Checklist Before Finalization

As a receptionist, I want a pending checklist, so no valid in-house order is left unbilled accidentally.

Acceptance Criteria:
- Before finalization, system shows pending vs billed order count.
- Finalization warning appears if pending in-house orders exist.
- User can proceed only after explicit confirmation when pending items remain.

## Epic 3: Optional In-House Pharmacy Billing Extension

Objective: Add configurable pharmacy charging into the same OPD ledger without forcing pharmacy complexity on all clinics.

### Story 3.1: Enable Pharmacy Module via Clinic Setting

As an admin, I want pharmacy billing to be configurable, so clinics can enable it only when needed.

Acceptance Criteria:
- Feature flag at clinic level: pharmacy billing enabled or disabled.
- When disabled, pharmacy charge UI is hidden.
- When enabled, pharmacy lines can be added to OPD ledger.

### Story 3.2: Add Prescription-Linked Pharmacy Lines

As a receptionist or pharmacy user, I want prescription-linked medicine charges, so billing is consistent with doctor prescriptions.

Acceptance Criteria:
- System can pull prescribed medicines into billable list.
- Quantity, rate, and line total are editable by permitted role.
- All pharmacy lines are included in consolidated invoice.

### Story 3.3: Handle Non-Stock or Unavailable Items

As a receptionist or pharmacy user, I want unavailable items flagged, so billing and fulfillment remain transparent.

Acceptance Criteria:
- Out-of-stock lines are visibly marked.
- User can remove, substitute, or mark as external purchase.
- Action selected is reflected in final bill notes.

## Epic 4: Payments, Controls, and Day-End Reliability

Objective: Complete checkout reliability through payment handling, exception management, audit controls, and closure reports.

### Story 4.1: Mixed Payment Collection and Settlement

As a receptionist, I want UPI, cash, card, and split payments, so patients can pay through preferred mode.

Acceptance Criteria:
- Payment modes supported: UPI, cash, card, split.
- Transaction reference captured for digital modes.
- Bill status updates to paid, partially paid, or due.

### Story 4.2: Payment Failure and Retry Handling

As a receptionist, I want safe retry flow for failed digital payments, so I can close bills confidently.

Acceptance Criteria:
- Failed or timeout payments are marked pending-failed, not paid.
- Retry action is available without duplicating paid status.
- Audit log captures each attempt and final state.

### Story 4.3: Controlled Amendments, Cancel, Refund, Reprint

As authorized staff, I want controlled post-billing actions, so corrections are possible without losing audit integrity.

Acceptance Criteria:
- Role-based permission for amend, cancel, refund, and reprint.
- Every action records reason, actor, and timestamp.
- Original bill snapshot remains immutable for audit.

### Story 4.4: Day-End Reconciliation Dashboard

As a receptionist or admin, I want day-end reconciliation, so I can verify collections and detect leakage.

Acceptance Criteria:
- Report by date and user: billed amount, collected amount, due amount, cancellation and refund totals.
- Payment-mode-wise split visible.
- Ordered vs billed diagnostics variance report available.

## Epic 5: Reception UX, Training, and Adoption Readiness

Objective: Maximize adoption through front-desk optimized UX and go-live support.

### Story 5.1: One-Screen Reception Billing Workspace

As a receptionist, I want one-page workflow for search, charge addition, and finalization, so checkout is faster.

Acceptance Criteria:
- Workspace includes patient search, OPD ledger view, pending items, payment pane, and finalize action.
- Minimal-click flow validated for common case.
- Keyboard-friendly controls for high-volume operations.

### Story 5.2: Role-Based SOP and Guided Tooltips

As a new user, I want guided SOP hints, so I can perform billing steps correctly with minimal training.

Acceptance Criteria:
- Inline guidance shown for critical actions.
- Contextual warnings for irreversible operations.
- SOP quick-help section available in billing workspace.

### Story 5.3: Go-Live Monitoring Metrics

As product and operations team, I want adoption metrics, so we can tune workflow quickly after release.

Acceptance Criteria:
- Tracks checkout time, amendment rate, failed payment rate, and pending-charge override rate.
- Daily trend view for first 30 and 90 days.
- Alert threshold for abnormal variance.

## Suggested Sprint Sequence

### Sprint 1

- Stories 1.1, 1.2, 1.3, 1.4
- Baseline: OPD ledger + fee capture + consolidated invoice

### Sprint 2

- Stories 2.1, 2.2, 2.3, 4.1
- Baseline: consultation order billing + duplicate prevention + mixed payments

### Sprint 3

- Stories 4.2, 4.3, 4.4, 5.1
- Baseline: reliability controls + day-end + one-screen reception workspace

### Sprint 4

- Stories 3.1, 3.2, 3.3, 5.2, 5.3
- Baseline: optional pharmacy + adoption hardening

## Definition of Done for This Backlog

- All must-build stories in Epics 1, 2, and 4 are complete
- End-to-end flow validated: register -> optional repeat fee -> doctor order handoff -> add charges -> payment -> consolidated bill
- Audit trail complete for all financial mutations
- Day-end reconciliation report operational
- First-30-day KPI dashboard enabled
