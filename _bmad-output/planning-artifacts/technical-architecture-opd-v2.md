# Technical Architecture v2: OPD Management System

## 1. Architectural Style
- Domain-oriented modular monolith for MVP with clear bounded contexts.
- Event-driven integration boundaries for billing, HIS, LIS, and notifications.
- Migration path to service decomposition after proven load and team scaling.

Rationale:
- Faster delivery and lower operational overhead in phase 1.
- Better transactional consistency for OPD workflows.
- Preserves future extraction boundaries.

## 2. Bounded Contexts
1. Patient Context
- Patient profile, identifiers, merge review, demographics.

2. Scheduling Context
- Doctor calendar, slot templates, leave/block windows.

3. Visit and Queue Context
- Check-in, token lifecycle, queue progression, no-show handling.

4. Clinical Context
- Consultation notes, diagnosis, vitals, follow-up.

5. Prescription and Orders Context
- Medication lines, dosage metadata, order requests.

6. Billing Integration Context
- Charge item composition, handoff events, retries, reconciliation.

7. IAM and Audit Context
- Authentication, role permissions, session controls, audit entries.

8. Reporting Context
- KPI projections, query views, exports.

## 3. Runtime Topology
- Web App (Django templates + HTMX for progressive interactivity)
- API App (Django + Django REST Framework)
- PostgreSQL (primary transactional store)
- Redis (cache + ephemeral queue state)
- Broker (RabbitMQ for domain/integration events)
- Object Store (document/attachment artifacts)
- Observability stack (OpenTelemetry collector + Prometheus + Grafana + centralized logs)

## 4. Data Architecture
## 4.1 Primary Stores
- PostgreSQL schemas:
  - identity
  - patient
  - scheduling
  - visit_queue
  - clinical
  - prescription
  - billing
  - reporting
  - audit

## 4.2 Data Ownership Rules
- Every table has one owning context.
- Cross-context reads use API or read-model projection.
- No direct write access across context boundaries.

## 4.3 Idempotency and Concurrency
- All create/update command endpoints accept Idempotency-Key header.
- Row versioning via optimistic locking on mutable records.
- Queue operations enforce atomic transitions in database transaction.

## 5. Security Architecture
- OIDC authentication with short-lived access tokens.
- Fine-grained authorization policy at API handler layer.
- PHI fields encrypted at rest using managed KMS keys.
- TLS 1.2+ for all north-south traffic, mTLS for east-west when split services are introduced.
- Security event logging for auth failures, privilege changes, record amendments, and export actions.

## 6. Reliability and Recovery
- Availability target: 99.9% monthly.
- Multi-AZ deployment for stateless API and broker.
- PostgreSQL PITR enabled with 15-minute backup cadence.
- RPO <= 15 minutes, RTO <= 60 minutes.
- Retry policy with exponential backoff + dead letter queues for integrations.

## 7. Performance Strategy
- Target <= 2s P95 for transactional endpoints.
- Queue board updates via websocket channel backed by Redis pub/sub.
- Reporting uses read-model tables refreshed incrementally from events.
- Index strategy: MRN, phone, appointment date, doctor_id+slot_start, queue_status, visit_id.

## 8. Integration Strategy
- HIS and Billing integrations implemented through adapter interfaces.
- Canonical event envelope for all outbound events:
  - event_id
  - event_type
  - aggregate_id
  - occurred_at
  - schema_version
  - source
  - payload
- Contract versioning uses semantic version tag in payload metadata.

## 9. Deployment Architecture
- Environments: dev, qa, uat, preprod, prod.
- GitHub Actions pipeline:
  - lint + unit tests
  - SAST + dependency scan
  - build and image signing
  - integration tests
  - environment deployment with approval gates
- Release strategy: blue-green for API, rolling for workers.

## 10. Operability
- SLOs:
  - API request success rate >= 99.9%
  - Queue update latency <= 3s P95
  - Billing handoff success >= 99.5% daily
- Alerts:
  - High error rate
  - Queue lag threshold breach
  - Billing retry backlog growth
  - Export job timeout spikes
- Runbooks required for top P1 scenarios before go-live.

## 11. Technology Decisions
- Frontend: Django templates + HTMX + Bootstrap-compatible component library.
- Backend: Django + Django REST Framework.
- DB: PostgreSQL 15.
- Cache/Realtime: Redis 7.
- Broker: RabbitMQ.
- ORM: Django ORM.

Python baseline:
- Python 3.12 LTS runtime.

Trade-off note:
- A modular monolith is chosen for MVP speed and consistency. Service decomposition can start with Billing Integration and Reporting contexts once throughput and team size justify it.

## 12. Build Order
1. IAM and RBAC baseline
2. Patient registration/search
3. Scheduling and slotting
4. Queue workflows
5. Consultation and prescription
6. Billing handoff + reconciliation
7. Reporting and exports
8. Hardening (security, performance, DR drills)
