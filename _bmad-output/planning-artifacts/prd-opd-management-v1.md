# PRD v2 (Refined): OPD Management System

## 1. Product Summary
The OPD Management System is a hospital-grade outpatient operations platform covering registration, appointmenting, queue flow, consultation documentation, prescription, and billing handoff in one auditable workflow.

This PRD is designed for production implementation and phased rollout, with measurable outcomes, quality gates, and operational controls.

## 2. Business Outcomes and KPIs
### 2.1 Target Outcomes (First 6 Months After Go-Live)
- Reduce average patient waiting time by 30%
- Increase doctor slot utilization to at least 85%
- Achieve at least 95% digital OPD encounter capture
- Reduce registration-to-consultation leakage by 40%
- Improve billing handoff success to at least 99.5%

### 2.2 KPI Definitions
- Waiting Time: Time from registration completion to consultation start
- Slot Utilization: Used slots / configured slots by doctor per day
- Digital Capture: OPD encounters fully documented in system / total OPD encounters
- Handoff Success: Successful billing handoff events / total consultation completions

## 3. Users, Personas, and Core Needs
### 3.1 Reception Staff
- Fast patient search and registration with de-duplication safeguards
- Simple slot booking and token generation for walk-ins

### 3.2 Doctor/Consultant
- Immediate access to patient context and visit history
- Low-friction note capture with specialty templates
- Rapid e-prescription and follow-up creation

### 3.3 Nurse/Triage Staff
- Vitals and pre-consultation capture with role-based access
- Queue status visibility and rooming support

### 3.4 Billing Desk
- Reliable consultation closure and chargeable item visibility
- Retry and exception handling for failed handoffs

### 3.5 Operations and Leadership
- Real-time OPD dashboard for throughput, waits, and bottlenecks
- Daily and weekly trend reporting for decisions

### 3.6 IT and Compliance
- Enforceable access policies, auditability, and operational telemetry

## 4. Scope
### 4.1 In Scope (MVP)
- Patient registration and patient search
- Doctor schedule and slot configuration
- Appointment booking and walk-in token management
- Queue board and patient call flow
- Consultation documentation
- e-Prescription and basic orders (lab/radiology request initiation)
- Billing handoff integration
- Role-based access control and audit logs
- Operational reporting dashboard

### 4.2 Out of Scope (MVP)
- Inpatient (IPD) workflows
- Complete enterprise EHR replacement
- Insurance adjudication workflow engine
- AI-assisted diagnosis or treatment recommendations

## 5. End-to-End User Journeys
### 5.1 Scheduled OPD Visit
1. Reception verifies patient profile and books/validates appointment.
2. Patient arrives and is checked in.
3. Queue token is generated and displayed.
4. Doctor conducts consultation and records findings.
5. Prescription/orders are generated.
6. Consultation completion triggers billing handoff.

### 5.2 Walk-In OPD Visit
1. Reception registers or searches patient.
2. Walk-in token is issued under configured priority rules.
3. Queue is managed with call/skip/recall.
4. Consultation and closure follow standard flow.

### 5.3 Failure/Exception Path
1. Billing handoff fails due to integration issue.
2. System flags failure and records reason.
3. Authorized user retries or resolves manually with audit trail.

## 6. Functional Requirements and Acceptance Criteria
### FR-1 Patient Registration and Search
Requirements:
- Create/edit patient profiles with mandatory demographics and identifiers.
- Search by MRN, mobile, and name plus date of birth.
- Provide probable duplicate detection and merge review flow.

Acceptance Criteria:
- New registration completes within 90 seconds median for trained staff.
- Search returns results in under 2 seconds P95.
- Duplicate warning triggers when configurable match threshold is crossed.

### FR-2 Scheduling and Slot Management
Requirements:
- Configure calendars, working windows, breaks, leaves, and overrides.
- Define slot duration by specialty and consultation type.
- Allow emergency slot insertion with audit log.

Acceptance Criteria:
- Slot changes are visible to booking screens within 5 seconds.
- All schedule edits capture user, timestamp, and reason.

### FR-3 Appointment and Walk-In Management
Requirements:
- Book/reschedule/cancel appointments.
- Handle walk-in registration and tokening.
- Enforce configurable overbooking constraints.

Acceptance Criteria:
- Reschedule and cancellation flows preserve activity history.
- Overbooking beyond configured limits is blocked by default policy.

### FR-4 Queue and Token Operations
Requirements:
- Display real-time queue by doctor/room.
- Support call next, skip, recall, and mark no-show.
- Estimate wait time using queue depth and average consult duration.

Acceptance Criteria:
- Queue state refresh latency is under 3 seconds P95.
- Call events are reflected on operator and display screens consistently.

### FR-5 Consultation Workspace
Requirements:
- Capture complaints, findings, diagnosis, notes, follow-up date.
- Capture triage/vitals for allowed roles.
- Autosave drafts and allow controlled amendments.

Acceptance Criteria:
- Draft autosave interval is no more than 15 seconds.
- Amendments require reason entry and are fully audit logged.

### FR-6 e-Prescription and Orders
Requirements:
- Generate prescription with medicine, dose, route, frequency, and duration.
- Print/share prescription as configured.
- Create basic lab/radiology order requests.

Acceptance Criteria:
- Prescription generation succeeds for at least 99.9% of finalized consults.
- Exported/printed format follows hospital-approved template.

### FR-7 Billing Handoff
Requirements:
- Emit completion event with consultation metadata and chargeables.
- Integrate with billing via API/event/file adapter.
- Maintain retry queue and reconciliation views.

Acceptance Criteria:
- Handoff success rate is at least 99.5% daily.
- Failed handoffs are visible with retriable status and reason code.

### FR-8 Reporting and Dashboards
Requirements:
- Daily operational view: volume, wait times, no-show rate, doctor utilization.
- Filters by date range, specialty, doctor, and location.
- CSV/PDF export for approved roles.

Acceptance Criteria:
- Dashboard load time under 4 seconds P95 for daily range.
- Export jobs complete in under 60 seconds for standard data volume.

### FR-9 Access Control and Auditability
Requirements:
- Enforce RBAC per module and action.
- Log sensitive actions and data edits.
- Control session timeout, re-auth for sensitive actions, and logout-all.

Acceptance Criteria:
- Unauthorized actions return deterministic deny response and are logged.
- Audit logs support filter by user, patient, action, and time window.

## 7. Non-Functional Requirements
### NFR-1 Performance
- Core transactions under 2 seconds P95 under expected load.
- Queue updates propagated under 3 seconds P95.

### NFR-2 Availability and Resilience
- 99.9% monthly uptime target.
- RPO 15 minutes or less, RTO 60 minutes or less.
- Graceful degradation for non-critical integrations.

### NFR-3 Security and Privacy
- Encryption in transit and at rest.
- Strong authentication with session controls.
- Least-privilege authorization and periodic access review.

### NFR-4 Scalability
- MVP for one hospital and one specialty with path to multi-site scale.
- Horizontal scaling for stateless APIs and event consumers.

### NFR-5 Observability and Operability
- Structured logs, traces, and service metrics.
- Alerts on SLA breaches, queue lag, and integration failures.
- Runbooks for top incident classes.

## 8. Integrations and Data Contracts
- HIS: Patient master sync and doctor/department metadata
- Billing: Consultation closure and chargeable handoff
- Optional (Phase 2): LIS and Pharmacy integration
- Notifications: SMS/WhatsApp provider for reminders and status

Each integration must define:
- Interface mode (API/event/file)
- Contract versioning policy
- Retry and dead-letter handling
- Operational ownership and escalation path

## 9. Compliance and Governance
- Follow applicable healthcare privacy and retention obligations.
- Maintain consent, disclosure, and amendment logs.
- Support legal hold and secure archival policy.
- Restrict production PHI access with break-glass controls.

## 10. Dependencies and Assumptions
### 10.1 Dependencies
- Billing system integration interface availability
- Identity provider and role source readiness
- Doctor schedule master data completeness

### 10.2 Assumptions
- Pilot specialty and site are confirmed before build freeze.
- Operational stakeholders are available for UAT and workflow sign-off.

## 11. Release Plan
### Phase 0: Foundation (2-4 Weeks)
- Finalize PRD, architecture, and integration contracts
- Define test data strategy and baseline KPIs

### Phase 1: MVP Build (8-12 Weeks)
- Build FR-1 to FR-9 with one-specialty pilot constraints
- Execute SIT, UAT, and security hardening

### Phase 2: Stabilization (4-6 Weeks)
- Hypercare, operational tuning, and backlog hardening
- Expand dashboards and integration reliability

### Phase 3: Scale-Out
- Add specialties/sites and optional integrations

## 12. MVP Exit Criteria
- End-to-end OPD flow live for pilot specialty.
- At least 95% digital encounter capture in pilot window.
- Handoff success at least 99.5% with reconciliation controls.
- Security, compliance, and DR readiness sign-off completed.
- No open Sev-1 defects at go-live decision point.

## 13. Risks and Mitigations
- Staff adoption risk: role-based training and on-floor hypercare.
- Data quality risk: validation rules and mandatory field policies.
- Integration instability risk: adapter retries, circuit breakers, dead-letter queues.
- Compliance risk: audit reviews and periodic access audits.

## 14. Open Decisions
- Notification provider selection (build vs buy)
- Hosting model (on-prem, cloud, or hybrid)
- Multi-tenant roadmap for group hospital rollouts
