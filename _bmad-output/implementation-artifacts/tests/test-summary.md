# Test Automation Summary

## Scope
This summary is generated from planning artifacts for the OPD Management System before code implementation starts.

Input artifacts:
- _bmad-output/planning-artifacts/epics.md
- _bmad-output/planning-artifacts/prd-opd-management-v1.md
- _bmad-output/planning-artifacts/technical-architecture-opd-v2.md

## Current State
- Application source code is not yet scaffolded in this workspace.
- Test automation frameworks are not yet configured in project code.
- Story definitions now include Unit, Integration, and E2E test scenarios per story.

## Recommended Test Stack (Django)
- Unit/Integration: pytest + pytest-django
- API contract tests: pytest + DRF APIClient
- E2E tests: Playwright (Python) against Django server
- Optional factories: factory_boy
- Coverage: coverage.py + pytest-cov

## Scenario Coverage from Story Definitions

### Epic 1: Intake and Identity
- Story 1.1: RBAC policy resolution, auth guard integration, role-based UI visibility E2E
- Story 1.2: duplicate matcher unit, patient create duplicate warning integration, registration duplicate-flow E2E
- Story 1.3: search query builder unit, audit logging integration, multi-key search E2E

### Epic 2: Scheduling and Queue
- Story 2.1: slot generation unit, schedule versioning integration, scheduler workflow E2E
- Story 2.2: appointment state machine unit, overbooking rule integration, appointment lifecycle E2E
- Story 2.3: queue transition unit, realtime queue event integration, queue board operation E2E

### Epic 3: Consultation and Prescription
- Story 3.1: autosave unit, finalize lock integration, consultation authoring E2E
- Story 3.2: amendment diff/validation unit, amendment audit integration, amend-with-reason E2E
- Story 3.3: prescription formatter unit, persistence/integration payload contract integration, prescription issue E2E

### Epic 4: Billing Handoff
- Story 4.1: payload mapper unit, adapter status integration, visit-close handoff E2E
- Story 4.2: retry scheduler unit, dead-letter integration, outage-retry-deadletter E2E
- Story 4.3: reconciliation filter unit, manual retry integration, billing console retry E2E

### Epic 5: Reporting and Governance
- Story 5.1: KPI aggregation unit, reporting API filter integration, dashboard filtering E2E
- Story 5.2: export payload validator unit, export/audit integration, report export E2E
- Story 5.3: alert evaluator unit, alert channel integration, incident-trigger E2E

## Next Steps
1. Scaffold Django application and test directories.
2. Configure pytest, pytest-django, and Playwright Python in CI.
3. Convert story-level scenarios into executable test specs per story key.
4. Gate merges on unit + integration pass; run E2E on staging environment.
