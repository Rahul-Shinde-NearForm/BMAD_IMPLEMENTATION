# Component Structure v1: OPD Management System

## 1. Repository Layout

```text
opd-management-system/
  apps/
    web-portal/
      src/
        app/
        modules/
          auth/
          patient/
          scheduling/
          queue/
          consultation/
          prescription/
          billing/
          reports/
        shared/
          ui/
          hooks/
          api/
          utils/
    api/
      src/
        main.ts
        modules/
          auth/
          patient/
          scheduling/
          appointment/
          queue/
          consultation/
          prescription/
          billing/
          reporting/
          audit/
        common/
          config/
          middleware/
          guards/
          interceptors/
          errors/
          events/
  packages/
    contracts/
      openapi/
      events/
      schemas/
    ui-kit/
    eslint-config/
    tsconfig/
  infra/
    kubernetes/
    terraform/
    observability/
  docs/
    architecture/
    runbooks/
```

## 2. Frontend Component Structure
## 2.1 Module Pattern
Each feature module follows:
- pages
- components
- api
- state
- validation
- tests

Example:

```text
modules/patient/
  pages/
    PatientSearchPage.tsx
    PatientRegistrationPage.tsx
  components/
    PatientSearchForm.tsx
    PatientListTable.tsx
    DuplicateWarningModal.tsx
  api/
    patientApi.ts
  state/
    patientStore.ts
  validation/
    patientSchemas.ts
  tests/
    patient-registration.spec.tsx
```

## 2.2 Shared UI Components
- DataTable
- FormField
- DateTimePicker
- TokenBadge
- QueueBoardWidget
- AuditTimeline
- ErrorBoundary

## 2.3 Frontend State Boundaries
- Server state with query cache (TanStack Query)
- UI state local to pages/components
- Auth and session state in global store

## 3. Backend Component Structure
## 3.1 Module Internals
Each backend module follows:
- controller
- service
- repository
- dto
- mapper
- policy
- events
- tests

Example:

```text
modules/queue/
  queue.controller.ts
  queue.service.ts
  queue.repository.ts
  dto/
    queue-action.request.ts
    queue-board.response.ts
  policy/
    queue.policy.ts
  events/
    queue-events.publisher.ts
  tests/
    queue.service.spec.ts
```

## 3.2 Cross-Cutting Components
- AuthGuard and RoleGuard
- RequestContext middleware (correlation id, actor info)
- ErrorMapper and exception filter
- AuditLogger interceptor
- MetricsPublisher

## 4. Domain Aggregates
- PatientAggregate
- ScheduleAggregate
- AppointmentAggregate
- VisitQueueAggregate
- ConsultationAggregate
- PrescriptionAggregate
- BillingHandoffAggregate

Rule:
- Aggregate boundaries map to transaction boundaries.

## 5. Database Component Structure
## 5.1 Core Tables
- patients
- patient_identifiers
- doctors
- schedules
- slots
- appointments
- visits
- queue_events
- consultations
- prescriptions
- prescription_items
- billing_handoffs
- audit_entries

## 5.2 Read Model Tables
- rm_opd_daily_metrics
- rm_doctor_utilization
- rm_queue_wait_summary

## 6. Integration Components
- BillingAdapter
- HisAdapter
- NotificationAdapter

Each adapter has:
- client
- mapper
- retry-policy
- health-check

## 7. Event Processing Components
- OutboxPublisherWorker
- IntegrationConsumerWorker
- DeadLetterReprocessor

## 8. Testing Components
- Unit tests in each module
- API contract tests in packages/contracts
- Integration tests for adapters
- E2E scenario tests for patient journeys

## 9. Ownership Matrix
- Patient/Scheduling/Queue: Core backend team
- Consultation/Prescription: Clinical workflow squad
- Billing adapter: Integrations squad
- Reporting/Audit: Platform squad

## 10. Coding Standards Baseline
- Strict TypeScript mode
- Lint and format checks enforced in CI
- Backward-compatible API change policy for v1
- Mandatory tests for new endpoints and critical bug fixes
