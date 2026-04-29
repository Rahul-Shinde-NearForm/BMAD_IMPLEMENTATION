conti---
stepsCompleted:
  - step-01-validate-prerequisites
  - step-02-design-epics
  - step-03-create-stories
  - step-04-final-validation
inputDocuments:
  - /Users/rahulshinde/OPD_MANAGEMENT_SYSTEM/_bmad-output/planning-artifacts/prd-opd-management-v1.md
  - /Users/rahulshinde/OPD_MANAGEMENT_SYSTEM/_bmad-output/planning-artifacts/technical-architecture-opd-v2.md
---

# OPD_MANAGEMENT_SYSTEM - Epic Breakdown

## Overview

This document provides the complete epic and story breakdown for OPD_MANAGEMENT_SYSTEM, decomposing the requirements from the PRD, UX Design if it exists, and Architecture requirements into implementable stories.

## Realignment Update (April 2026)

The story plan has been realigned to reflect implemented Indian OPD workflow requirements raised during execution.

### Delivery Status Snapshot

- Completed: Stories 1.1, 1.2, 1.3
- Completed: Stories 2.1, 2.2, 2.3
- Completed: Stories 3.1, 3.2, 3.3
- Completed: Stories 4.1, 4.2, 4.3
- Completed (started and delivered): Story 5.1
- Pending: Stories 5.2, 5.3

### Scope Realignment Notes

- Appointment lifecycle now includes COMPLETED status marked by doctor after consultation.
- OPD Number is generated per appointment as unique OPD-XXXXXXXX identifier for visit tracking.
- Reception workflow includes repeat patient OPD history retrieval and patient demographic update support.
- Reception workflow includes next-day patient reminder call list API with mobile numbers.
- Prescription print layout aligned to requested Indian OPD style (Diagnosis heading, no UHID/MRN, simplified medicine table).

## Requirements Inventory

### Functional Requirements

FR1: The system shall create and edit patient profiles with mandatory demographics and identifiers, including duplicate detection and merge review.
FR2: The system shall support patient search by MRN, mobile number, and name plus date of birth with performant lookup.
FR3: The system shall manage doctor scheduling, including working windows, breaks, leave, and slot duration by specialty/consultation type.
FR4: The system shall enable appointment lifecycle management (book, reschedule, cancel) and walk-in token generation with policy-based overbooking controls.
FR5: The system shall provide real-time queue operations, including call-next, skip, recall, and no-show handling with wait-time estimation.
FR6: The system shall provide consultation documentation with complaint, findings, diagnosis, notes, follow-up, and controlled amendments with auditability.
FR7: The system shall generate e-prescriptions and basic lab/radiology order requests in approved output formats.
FR8: The system shall perform billing handoff with integration adapters, retry/reconciliation support, and failure reason visibility.
FR9: The system shall provide operational reports and dashboards with role-based exports and filtering by date/specialty/doctor/location.
FR10: The system shall enforce RBAC, session security controls, and comprehensive audit logging for sensitive actions.

### NonFunctional Requirements

NFR1: Core transactional API actions shall meet <= 2 seconds P95 latency.
NFR2: Queue state propagation shall meet <= 3 seconds P95 latency.
NFR3: System availability target shall be 99.9% monthly uptime.
NFR4: Disaster recovery objectives shall meet RPO <= 15 minutes and RTO <= 60 minutes.
NFR5: Security shall include encryption in transit and at rest, strong authentication, and least-privilege authorization.
NFR6: System shall support one-site MVP with architecture that scales horizontally for future multi-site expansion.
NFR7: Observability shall include structured logs, traces, metrics, and actionable alerts for SLA breaches and integration failures.
NFR8: Billing handoff reliability shall achieve >= 99.5% daily success with retriable failure handling.
NFR9: Compliance controls shall support consent/disclosure traceability, auditability, and secure archival/legal-hold constraints.

### Additional Requirements

- Architecture shall follow a domain-oriented modular monolith in MVP with bounded contexts for Patient, Scheduling, Visit/Queue, Clinical, Prescription/Orders, Billing Integration, IAM/Audit, and Reporting.
- Technology baseline shall use Python 3.12 with Django for both frontend and backend delivery.
- Frontend implementation shall use Django templates with HTMX for progressive interactivity.
- API implementation shall use Django REST Framework for versioned HTTP contracts.
- Data layer shall use PostgreSQL 15 with context-owned schemas and explicit ownership boundaries.
- ORM standard shall be Django ORM; cross-context writes are forbidden.
- Redis shall support cache/realtime concerns; RabbitMQ shall carry integration/domain events.
- Idempotency-Key header is mandatory for create/update command endpoints.
- Queue transitions shall be atomic and enforce optimistic concurrency for mutable records.
- Integrations shall use adapter interfaces and canonical event envelope/versioning metadata.
- Deployment pipeline shall enforce unit/integration/security scans and gated environment promotion.
- Operability shall include SLO monitoring, alerting, and runbook readiness before go-live.

### UX Design Requirements

- No dedicated UX design document was discovered in planning artifacts at this time.

### FR Coverage Map

FR1: Epic 1 - Secure OPD Intake and Identity Control (patient profile create/edit and dedupe workflow)
FR2: Epic 1 - Secure OPD Intake and Identity Control (multi-key patient search and lookup performance)
FR3: Epic 2 - Appointment Scheduling and Queue Operations (doctor schedule and slot configuration)
FR4: Epic 2 - Appointment Scheduling and Queue Operations (appointment lifecycle and walk-in controls)
FR5: Epic 2 - Appointment Scheduling and Queue Operations; Epic 3 - Clinical Consultation and Prescription Workflow (queue operations and consult flow boundary)
FR6: Epic 3 - Clinical Consultation and Prescription Workflow (consultation recording and amendments)
FR7: Epic 3 - Clinical Consultation and Prescription Workflow (e-prescription and basic order entry)
FR8: Epic 4 - Billing Handoff and Reconciliation Reliability (handoff, retries, and exception handling)
FR9: Epic 5 - Operational Insights, Exports, and Production Governance (dashboards, reporting, and exports)
FR10: Epic 1 - Secure OPD Intake and Identity Control; Epic 5 - Operational Insights, Exports, and Production Governance (RBAC and audit governance)

## Epic List

### Epic 1: Secure OPD Intake and Identity Control
Enable reception and authorized staff to securely onboard and search patients while enforcing role-based access and audit controls from day one.
**FRs covered:** FR1, FR2, FR10

### Epic 2: Appointment Scheduling and Queue Operations
Enable staff to configure doctor availability, manage appointments and walk-ins, and run real-time queue/token operations for OPD flow.
**FRs covered:** FR3, FR4, FR5

### Epic 3: Clinical Consultation and Prescription Workflow
Enable doctors and nurses to complete consultation documentation, controlled amendments, and e-prescription/basic orders in a single visit flow.
**FRs covered:** FR5, FR6, FR7

### Epic 4: Billing Handoff and Reconciliation Reliability
Enable reliable financial closure for OPD visits through robust billing handoff, retries, and reconciliation workflows.
**FRs covered:** FR8

### Epic 5: Operational Insights, Exports, and Production Governance
Enable operations and leadership to monitor KPIs, export reports, and maintain compliance-grade observability and audit governance.
**FRs covered:** FR9, FR10

## Epic 1: Secure OPD Intake and Identity Control

Enable reception and authorized staff to securely onboard and search patients while enforcing role-based access and audit controls from day one.

### Story 1.1: Configure Django Identity and RBAC Foundation

As an IT administrator,
I want role-based access and authentication policies configured,
So that only authorized users can access OPD modules safely.

**Acceptance Criteria:**

**Given** a fresh OPD deployment
**When** an administrator creates roles for Reception, Doctor, Nurse, Billing, and Admin
**Then** each role is persisted with scoped permissions per module
**And** unauthorized endpoint access is denied and logged.

**Test Scenarios:**

- Unit: Role policy resolver grants and denies module actions according to configured permission matrix.
- Integration: Auth service + RBAC middleware denies protected API access for users without mapped roles.
- E2E: Admin creates roles and assigns a user; user login shows only allowed modules and blocked navigation returns access denied.

### Story 1.2: Register Patient with De-duplication Controls

As a reception user,
I want to register a patient with duplicate warnings,
So that records remain accurate and non-redundant.

**Acceptance Criteria:**

**Given** a reception user submits patient demographics and identifiers
**When** the submitted values match an existing patient above threshold
**Then** the system shows duplicate warning options before final save
**And** the user can continue with explicit confirmation or open merge review.

**Test Scenarios:**

- Unit: Duplicate matcher returns probable duplicate candidates when similarity threshold is met.
- Integration: Patient create endpoint with duplicate candidate triggers warning response contract and merge-review metadata.
- E2E: Reception enters near-duplicate patient details, sees duplicate modal, and selects continue or merge review successfully.

### Story 1.3: Multi-key Patient Search with Audit Trail

As a reception user,
I want to search patients by MRN, phone, and name plus DOB,
So that I can find the right record quickly and safely.

**Acceptance Criteria:**

**Given** the patient master contains existing records
**When** the user searches by supported key combinations
**Then** the system returns matching results within target response thresholds
**And** each search interaction is captured in the audit trail with actor and timestamp.

**Test Scenarios:**

- Unit: Search query builder composes filters for MRN, phone, and name plus DOB combinations.
- Integration: Search API persists audit event with actor, query type, and timestamp for each request.
- E2E: Reception searches by each supported key and verifies result list correctness and searchable patient selection flow.

## Epic 2: Appointment Scheduling and Queue Operations

Enable staff to configure doctor availability, manage appointments and walk-ins, and run real-time queue/token operations for OPD flow.

### Story 2.1: Configure Doctor Schedules and Slot Templates

As an admin scheduler,
I want to define doctor availability, breaks, and slot durations,
So that appointments and walk-ins align with real clinic capacity.

**Acceptance Criteria:**

**Given** a doctor profile exists
**When** the scheduler sets working windows, breaks, and slot duration
**Then** slot templates are generated for the selected date range
**And** schedule edits are versioned with user, timestamp, and reason.

**Test Scenarios:**

- Unit: Slot generator creates non-overlapping time slots from configured windows, breaks, and slot duration.
- Integration: Schedule update API writes versioned history entry with actor and reason.
- E2E: Scheduler updates doctor availability and confirms regenerated slots appear in booking UI for selected dates.

### Story 2.2: Manage Appointment Lifecycle and Walk-in Tokens

As a reception user,
I want to book, reschedule, cancel appointments and issue walk-in tokens,
So that patient intake remains controlled and trackable.

**Acceptance Criteria:**

**Given** slots are available for a doctor and date
**When** the user books, reschedules, or cancels an appointment
**Then** appointment status transitions are persisted with history
**And** overbooking rules are enforced according to configuration.
**And** each booked visit is assigned a unique OPD number for visit-level tracking.
**And** repeat visit booking can fetch prior OPD visit history for the patient.
**And** doctor can mark appointment as completed after consultation.

**Test Scenarios:**

- Unit: Appointment state machine enforces valid transitions (booked, rescheduled, cancelled).
- Integration: Booking endpoint rejects overbooking when policy threshold is exceeded.
- E2E: Reception books, reschedules, and cancels the same patient appointment with history visible at each step.
- Integration: Booking response includes generated OPD number and prior OPD history for repeat patients.
- Integration: Completion endpoint transitions appointment from booked or rescheduled to completed with audit event.

### Story 2.3: Run Live Queue Board Operations

As a queue operator,
I want call-next, skip, recall, and no-show controls,
So that patient flow remains smooth during OPD hours.

**Acceptance Criteria:**

**Given** a checked-in patient is in waiting state
**When** an operator performs a queue action
**Then** the visit queue status transitions atomically and is visible in real time
**And** the queue board updates within defined latency objectives.

**Test Scenarios:**

- Unit: Queue transition handler allows only valid actions (call-next, skip, recall, no-show).
- Integration: Queue action API updates queue state and publishes realtime event payload.
- E2E: Queue operator performs actions and queue board reflects updates for all active viewers.

## Epic 3: Clinical Consultation and Prescription Workflow

Enable doctors and nurses to complete consultation documentation, controlled amendments, and e-prescription/basic orders in a single visit flow.

### Story 3.1: Capture Consultation Notes with Controlled Drafting

As a doctor,
I want to document consultation details with autosave,
So that clinical records are complete without losing progress.

**Acceptance Criteria:**

**Given** a visit is in consultation state
**When** a doctor enters complaint, findings, diagnosis, and notes
**Then** the draft is autosaved at configured intervals
**And** finalization locks the consultation record from silent edits.

**Test Scenarios:**

- Unit: Consultation draft autosave service persists incremental changes per interval.
- Integration: Finalize consultation endpoint transitions status to finalized and blocks direct edit requests.
- E2E: Doctor enters notes, observes autosave indicator, finalizes consultation, and is prevented from silent post-finalization edits.

### Story 3.2: Record Vitals and Amend Consultation with Reason

As a nurse or doctor,
I want to capture vitals and perform controlled amendments,
So that records stay clinically accurate and traceable.

**Acceptance Criteria:**

**Given** role permissions allow triage and amendment actions
**When** vitals are entered or finalized notes are amended
**Then** the system stores old and new values with reason code
**And** amendment events are added to the audit timeline.

**Test Scenarios:**

- Unit: Amendment validator requires reason code and captures diff between previous and new values.
- Integration: Amendment API writes audit timeline records with actor, reason, and field-level changes.
- E2E: Nurse records vitals, doctor amends finalized note with reason, and audit timeline displays amendment event.

### Story 3.3: Issue E-prescription and Basic Orders

As a doctor,
I want to create prescriptions and basic lab/radiology orders,
So that treatment instructions are completed within the same visit.

**Acceptance Criteria:**

**Given** a consultation is finalized
**When** prescription items and order requests are submitted
**Then** a prescription artifact is generated in approved format
**And** medication/order payloads are stored for downstream integration.
**And** printable prescription output follows configured Indian OPD layout requirements.

**Test Scenarios:**

- Unit: Prescription formatter validates required medication attributes and output template rendering.
- Integration: Prescription/order submit endpoint stores structured payload and links to visit/consultation IDs.
- E2E: Doctor issues prescription and basic order request, then downloads/prints the generated artifact successfully.
- E2E: Printed prescription renders diagnosis-first layout and excludes UHID or MRN when configured for local workflow.

## Epic 4: Billing Handoff and Reconciliation Reliability

Enable reliable financial closure for OPD visits through robust billing handoff, retries, and reconciliation workflows.

### Story 4.1: Publish Consultation Completion for Billing Handoff

As a billing integration worker,
I want finalized visits to produce billing handoff payloads,
So that financial processing starts automatically.

**Acceptance Criteria:**

**Given** a visit has finalized consultation and chargeable data
**When** billing handoff is triggered
**Then** a canonical payload is sent through configured adapter channel
**And** handoff status is persisted as pending, success, or failed.

**Test Scenarios:**

- Unit: Billing payload mapper produces canonical event with required fields and schema version.
- Integration: Billing adapter call updates handoff status lifecycle based on provider response.
- E2E: Completing consultation triggers billing handoff and billing status becomes visible in operational console.

### Story 4.2: Implement Retry Queue and Dead-letter Handling

As an integration operator,
I want automatic retries with dead-letter capture,
So that transient failures do not cause revenue leakage.

**Acceptance Criteria:**

**Given** a billing handoff fails with retriable error
**When** retry policy executes
**Then** exponential backoff attempts occur up to configured limit
**And** exhausted messages are moved to dead-letter with failure metadata.

**Test Scenarios:**

- Unit: Retry scheduler computes exponential backoff intervals and stop conditions correctly.
- Integration: Worker moves failed handoffs to dead-letter store after max retry attempts.
- E2E: Simulated billing outage causes retries and eventual dead-letter capture with failure reason visible.

### Story 4.3: Build Billing Reconciliation and Manual Retry Console

As a billing desk user,
I want visibility into failed handoffs with manual retry,
So that unresolved billing gaps can be closed quickly.

**Acceptance Criteria:**

**Given** failed or delayed handoff records exist
**When** billing user filters by status/date/reason and retries a record
**Then** status transitions and retry attempts are tracked
**And** reconciliation views show success rate and unresolved backlog.

**Test Scenarios:**

- Unit: Reconciliation filter logic returns correct subsets for status, date range, and reason filters.
- Integration: Manual retry endpoint appends retry audit entry and updates handoff status.
- E2E: Billing user filters failed handoffs, retries one item, and sees updated status and KPI counters.

## Epic 5: Operational Insights, Exports, and Production Governance

Enable operations and leadership to monitor KPIs, export reports, and maintain compliance-grade observability and audit governance.

### Story 5.1: Build OPD Daily Metrics Dashboard

As an operations manager,
I want daily KPIs for volume, wait time, no-shows, and utilization,
So that I can identify bottlenecks and improve throughput.

**Acceptance Criteria:**

**Given** OPD events are captured during clinic operations
**When** dashboard data is requested by permitted roles
**Then** metrics are rendered with filters for date, specialty, doctor, and location
**And** dashboard load meets defined performance thresholds.

**Test Scenarios:**

- Unit: KPI aggregator computes wait time, no-show rate, and utilization metrics accurately.
- Integration: Reporting API returns filtered metric payload aligned to role permissions.
- E2E: Operations user opens dashboard, applies filters, and verifies updated chart/table values load within target thresholds.

Implementation update: Daily metrics API delivered with date, specialty, doctor, and location filters, plus RBAC enforcement.

### Story 5.2: Provide Role-based Report Exports

As an admin user,
I want CSV/PDF export capability with audit logging,
So that operational reporting can be shared without losing governance.

**Acceptance Criteria:**

**Given** a user has report export permission
**When** an export job is requested with filters and format
**Then** export artifacts are generated and retrievable securely
**And** export initiation and download actions are audit logged.

**Test Scenarios:**

- Unit: Export job builder validates format and filter payload before queueing.
- Integration: Export service stores artifact metadata and audit entries for generate and download actions.
- E2E: Admin requests CSV and PDF exports, downloads files, and confirms export activity in audit view.

### Story 5.3: Enable Production Observability and Compliance Controls

As a platform owner,
I want SLO monitors, alerts, and compliance runbooks in place,
So that production OPD operations are reliable and auditable.

**Acceptance Criteria:**

**Given** production observability integrations are configured
**When** API errors, queue lag, or billing backlog breaches thresholds
**Then** alerts are raised to on-call channels with actionable context
**And** incident response follows documented runbooks with post-incident tracking.

**Test Scenarios:**

- Unit: Alert rule evaluator maps threshold breaches to correct severity and alert templates.
- Integration: Monitoring pipeline forwards alerts to configured notification channels with correlation context.
- E2E: Injected failure scenario triggers alert, creates incident record, and links to runbook workflow.
