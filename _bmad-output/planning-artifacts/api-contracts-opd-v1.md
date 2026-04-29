# API Contracts v1: OPD Management System

## 1. API Conventions
- Base URL: /api/v1
- Authentication: Bearer JWT
- Content type: application/json
- Idempotency: Idempotency-Key required for create command endpoints
- Correlation: X-Correlation-Id accepted and echoed
- Time format: ISO-8601 UTC

## 2. Error Model
All non-2xx responses follow:

```json
{
  "error": {
    "code": "string",
    "message": "string",
    "details": [],
    "correlationId": "string"
  }
}
```

Common codes:
- AUTH_UNAUTHORIZED
- AUTH_FORBIDDEN
- VALIDATION_FAILED
- RESOURCE_NOT_FOUND
- CONFLICT_STATE
- INTEGRATION_TIMEOUT
- INTERNAL_ERROR

## 3. Patient APIs
### 3.1 Create Patient
- POST /patients

Request:
```json
{
  "firstName": "Rahul",
  "lastName": "Shinde",
  "dob": "1991-01-02",
  "gender": "M",
  "phone": "+919999999999",
  "nationalId": "XXXX",
  "address": {
    "line1": "...",
    "city": "...",
    "state": "...",
    "postalCode": "..."
  }
}
```

Response 201:
```json
{
  "patientId": "pat_123",
  "mrn": "MRN-000123",
  "createdAt": "2026-04-29T10:00:00Z"
}
```

### 3.2 Search Patient
- GET /patients/search?mrn=&phone=&name=&dob=

Response 200:
```json
{
  "items": [
    {
      "patientId": "pat_123",
      "mrn": "MRN-000123",
      "fullName": "Rahul Shinde",
      "dob": "1991-01-02"
    }
  ]
}
```

## 4. Scheduling APIs
### 4.1 Upsert Doctor Schedule
- PUT /doctors/{doctorId}/schedule

Request:
```json
{
  "timezone": "Asia/Kolkata",
  "workingHours": [
    {"day": "MON", "start": "09:00", "end": "13:00"},
    {"day": "MON", "start": "15:00", "end": "18:00"}
  ],
  "slotMinutes": 10
}
```

Response 200:
```json
{
  "doctorId": "doc_1",
  "version": 3,
  "effectiveFrom": "2026-05-01"
}
```

### 4.2 List Available Slots
- GET /slots?doctorId=&date=&specialty=

Response 200:
```json
{
  "doctorId": "doc_1",
  "date": "2026-05-01",
  "slots": [
    {"slotId": "s1", "start": "2026-05-01T09:00:00Z", "status": "AVAILABLE"}
  ]
}
```

## 5. Appointment and Visit APIs
### 5.1 Book Appointment
- POST /appointments

Request:
```json
{
  "patientId": "pat_123",
  "doctorId": "doc_1",
  "slotId": "s1",
  "visitType": "FOLLOW_UP",
  "channel": "WALK_IN"
}
```

Response 201:
```json
{
  "appointmentId": "apt_101",
  "status": "BOOKED"
}
```

### 5.2 Check-In Visit
- POST /appointments/{appointmentId}/check-in

Response 200:
```json
{
  "visitId": "vis_5001",
  "tokenNumber": 32,
  "queueStatus": "WAITING"
}
```

## 6. Queue APIs
### 6.1 Get Queue Board
- GET /queues?doctorId=&roomId=

Response 200:
```json
{
  "doctorId": "doc_1",
  "nowServing": 30,
  "waiting": [31, 32, 33],
  "avgWaitMinutes": 14
}
```

### 6.2 Queue Action
- POST /queues/{visitId}/actions

Request:
```json
{
  "action": "CALL_NEXT",
  "reason": "optional"
}
```

Allowed actions:
- CALL_NEXT
- SKIP
- RECALL
- MARK_NO_SHOW
- COMPLETE

Response 200:
```json
{
  "visitId": "vis_5001",
  "queueStatus": "IN_CONSULT"
}
```

## 7. Consultation APIs
### 7.1 Save Consultation Draft
- PUT /visits/{visitId}/consultation

Request:
```json
{
  "chiefComplaint": "Fever",
  "vitals": {"temperature": 101.0, "bp": "120/80"},
  "diagnosis": ["Viral fever"],
  "notes": "Hydration advised",
  "followUpDate": "2026-05-04"
}
```

Response 200:
```json
{
  "consultationId": "con_12",
  "status": "DRAFT"
}
```

### 7.2 Finalize Consultation
- POST /visits/{visitId}/consultation/finalize

Response 200:
```json
{
  "consultationId": "con_12",
  "status": "FINALIZED",
  "finalizedAt": "2026-05-01T09:40:00Z"
}
```

## 8. Prescription APIs
### 8.1 Create Prescription
- POST /visits/{visitId}/prescriptions

Request:
```json
{
  "items": [
    {
      "drugCode": "PCM500",
      "drugName": "Paracetamol 500mg",
      "dose": "1 tablet",
      "frequency": "TID",
      "durationDays": 5,
      "route": "ORAL"
    }
  ]
}
```

Response 201:
```json
{
  "prescriptionId": "rx_111",
  "status": "ISSUED"
}
```

## 9. Billing Handoff APIs
### 9.1 Trigger Billing Handoff
- POST /visits/{visitId}/billing-handoff

Response 202:
```json
{
  "handoffId": "bh_100",
  "status": "PENDING"
}
```

### 9.2 Get Handoff Status
- GET /billing-handoffs/{handoffId}

Response 200:
```json
{
  "handoffId": "bh_100",
  "status": "FAILED",
  "failureCode": "REMOTE_TIMEOUT",
  "retryCount": 2,
  "lastTriedAt": "2026-05-01T10:10:00Z"
}
```

### 9.3 Retry Handoff
- POST /billing-handoffs/{handoffId}/retry

Response 202:
```json
{
  "handoffId": "bh_100",
  "status": "RETRY_QUEUED"
}
```

## 10. Reporting APIs
### 10.1 OPD Daily Metrics
- GET /reports/opd-daily?date=&specialty=&doctorId=

Response 200:
```json
{
  "date": "2026-05-01",
  "totalVisits": 220,
  "avgWaitMinutes": 18,
  "noShowRate": 0.07,
  "doctorUtilization": 0.86
}
```

### 10.2 Export Report
- POST /reports/exports

Request:
```json
{
  "reportType": "OPD_DAILY",
  "format": "CSV",
  "filters": {"dateFrom": "2026-05-01", "dateTo": "2026-05-07"}
}
```

Response 202:
```json
{
  "exportId": "exp_1",
  "status": "QUEUED"
}
```

## 11. Authorization Matrix (Summary)
- Reception: patient search/create, appointment booking, check-in
- Doctor: consultation create/finalize, prescription issue
- Nurse: vitals entry, queue assist actions
- Billing: handoff status and retry
- Admin: schedule config, role assignment, reports, audit view

## 12. Event Contracts
### 12.1 consultation.finalized.v1
```json
{
  "eventId": "evt_1",
  "eventType": "consultation.finalized.v1",
  "occurredAt": "2026-05-01T09:40:00Z",
  "payload": {
    "visitId": "vis_5001",
    "consultationId": "con_12",
    "doctorId": "doc_1",
    "patientId": "pat_123"
  }
}
```

### 12.2 billing.handoff.requested.v1
```json
{
  "eventId": "evt_2",
  "eventType": "billing.handoff.requested.v1",
  "occurredAt": "2026-05-01T09:41:00Z",
  "payload": {
    "visitId": "vis_5001",
    "handoffId": "bh_100",
    "charges": []
  }
}
```
