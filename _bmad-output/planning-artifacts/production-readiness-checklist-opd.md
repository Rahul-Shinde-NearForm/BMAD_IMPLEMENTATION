# Production Readiness Checklist: OPD Management System

## Governance and Scope
- Scope baseline approved (MVP + out-of-scope)
- Roles and RACI defined across product, engineering, clinical ops, IT, and compliance
- Release milestones and change control process approved

## Functional Completeness
- Registration, scheduling, queue, consultation, prescription, and billing handoff complete
- UAT sign-off from reception, doctors, billing, and admin stakeholders
- Accessibility and usability checks completed for core workflows

## Security and Compliance
- Threat model and risk register reviewed
- RBAC matrix approved and tested
- PHI encryption and key management validated
- Audit trail completeness and immutability validated
- Privacy and legal controls reviewed by compliance

## Reliability and Performance
- Load test passed for expected OPD peak concurrency
- P95 latency targets met for core APIs
- Queue update propagation SLA validated
- Failover and rollback plan tested

## Data and Integrations
- Master data migration validated
- Billing integration reconciliation accuracy >= 99.5%
- Notification workflows verified (if in scope)
- Backup, restore, and retention policy validated

## Observability and Operations
- Logs, metrics, traces, dashboards configured
- Alert thresholds tuned and tested
- On-call rotation and escalation matrix published
- Incident response runbooks available and reviewed

## Deployment Readiness
- CI/CD with quality gates and approvals enabled
- Infrastructure-as-code reviewed and reproducible
- Environment parity achieved (QA/UAT/Pre-Prod/Prod)
- Release rehearsal completed in pre-production

## Training and Adoption
- Role-based SOPs documented
- End-user training sessions completed
- Hypercare support window planned for launch

## Go-Live Exit Criteria
- No open Sev-1 or Sev-2 defects
- Compliance sign-off complete
- DR drill completed within agreed RTO/RPO
- Business owner and IT operations go-live approval captured
