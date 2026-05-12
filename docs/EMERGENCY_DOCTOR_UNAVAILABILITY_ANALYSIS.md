# Emergency Doctor Unavailability Feature - Comprehensive Analysis

**Date**: May 9, 2026  
**System**: OPD Management System  
**Status**: Requirements & Architecture Analysis

---

## Executive Summary

The Emergency Doctor Unavailability feature enables doctors to immediately cancel all of today's appointments due to emergencies, with the system automatically rescheduling them to subsequent days. A receptionist approval workflow handles capacity overflows, and audit trails track all changes. This is a **HIGH-COMPLEXITY, MEDIUM-EFFORT** feature requiring careful transaction handling and multi-step state management.

---

## 1. REQUIREMENTS CLARIFICATION

### 1.1 Critical Clarifications Needed

| Question | Current Assumption | Recommendation |
|----------|-------------------|-----------------|
| **What defines "day's capacity"?** | Total appointments for a doctor on a given date, compared to `daily_patient_capacity` field | Use `daily_patient_capacity` from DoctorScheduleTemplate (if exists) or Doctor.daily_patient_capacity as baseline. Capacity = max concurrent slots, NOT slot count. |
| **Skip limit for rescheduling** | Max 2-3 days ahead | Recommend: Try tomorrow → day-after → day-after-that (3-day window). Show "beyond capacity" alert if no slots in 3 days. |
| **Multi-day unavailability** | Out of scope for MVP | Recommend Phase 2: Add "Mark Doctor Unavailable (date range)" separate feature. MVP = single-day emergency only. |
| **Patient notification method** | SMS/WhatsApp/Email/In-app | Recommend: In-app notification + SMS (if phone exists). Email optional Phase 2. Assume SMS gateway available. |
| **Receptionist timeout** | How long to wait for approval? | Recommend: 30-minute auto-escalation to senior receptionist or clinic admin. Store pending state during waiting. |
| **Slot handling** | Which slots are freed when appointment is cancelled? | **DO NOT free slots**. Appointment marked RESCHEDULED preserves audit trail. Slots remain AVAILABLE for normal bookings. |

---

### 1.2 Recommended Business Rules (MVP)

1. **Cancellation Trigger**
   - Only doctor (or admin/clinic manager) can cancel their own appointments for today
   - Requires a confirmation modal (prevent accidental clicks)
   - Action logged with timestamp and reason

2. **Automatic Rescheduling**
   - Attempt sequence: Tomorrow → Day-after-tomorrow → Day-after-that
   - Use same time slot as original (e.g., if appt was 10:00-10:15, try to keep 10:00-10:15)
   - If exact slot unavailable, use "next available slot" on that date
   - Appointments remain in order (FIFO rescheduling)

3. **Capacity Check**
   - **Definition**: `appointments_booked_for_date + appointments_being_rescheduled > daily_patient_capacity`
   - Calculate BEFORE any reschedules are applied
   - If tomorrow capacity exceeded → trigger receptionist approval flow

4. **Receptionist Approval Options**
   - **Option A ("Approve & Exceed")**: All appointments stay on tomorrow, ignore capacity limit. Admin liability accepted.
   - **Option B ("Move Excess")**: Fill tomorrow to capacity, push remaining to day-after-tomorrow (and beyond if needed).
   - **No Reject**: Once initiated, reschedule cannot be cancelled (design decision: reduce patient disruption).

5. **Notifications**
   - **Patient**: "Your appointment on [original_date] with Dr. [name] has been rescheduled to [new_date] at [time]. [Clinic] has notified you of the change."
   - **Receptionist**: Real-time alert + email + dashboard badge
   - **Doctor**: Confirmation message when emergency cancellation completed

---

## 2. SYSTEM CHANGES NEEDED

### 2.1 Database Schema Changes

#### New Fields for Appointment Model

```python
class Appointment(models.Model):
    # ... existing fields ...
    
    # Emergency reschedule tracking
    rescheduled_due_to_emergency = models.BooleanField(default=False)
    original_slot_date = models.DateField(null=True, blank=True)  # Preserve original date
    original_start_time = models.TimeField(null=True, blank=True)
    original_end_time = models.TimeField(null=True, blank=True)
    
    # Reschedule reason & audit
    reschedule_reason = models.CharField(
        max_length=50, 
        choices=[
            ("ROUTINE", "Routine Reschedule"),
            ("EMERGENCY_DOCTOR", "Doctor Emergency"),
            ("EMERGENCY_PATIENT", "Patient Emergency"),
        ],
        default="ROUTINE"
    )
    rescheduled_at = models.DateTimeField(null=True, blank=True)
    rescheduled_by = models.ForeignKey(
        "auth.User", 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name="emergency_reschedules"
    )
```

#### New Model: DoctorEmergencyAction

Tracks bulk reschedule operations atomically:

```python
class DoctorEmergencyAction(models.Model):
    STATUS_CHOICES = [
        ("INITIATED", "Initiated - awaiting capacity check"),
        ("CAPACITY_EXCEEDED", "Capacity exceeded - awaiting approval"),
        ("APPROVED_EXCEED", "Approved to exceed capacity"),
        ("APPROVED_DISTRIBUTE", "Approved with distribution"),
        ("IN_PROGRESS", "Rescheduling in progress"),
        ("COMPLETED", "Completed successfully"),
        ("FAILED", "Failed - partial reschedule"),
        ("CANCELLED", "Cancelled by doctor/admin"),
    ]
    
    doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE, related_name="emergency_actions")
    action_date = models.DateField()  # Today's date (appointments on this date being cancelled)
    total_appointments = models.PositiveIntegerField()  # Count of appts being rescheduled
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    reason = models.TextField()  # Why the cancellation (medical emergency, etc.)
    
    # Capacity overflow info
    tomorrow_available_slots = models.PositiveIntegerField(default=0)
    tomorrow_capacity = models.PositiveIntegerField(default=0)
    capacity_exceeded_by = models.PositiveIntegerField(default=0)
    
    # Approval tracking
    approval_required = models.BooleanField(default=False)
    approval_method = models.CharField(
        max_length=20,
        choices=[("EXCEED", "Exceed Capacity"), ("DISTRIBUTE", "Distribute Across Days")],
        null=True,
        blank=True
    )
    approved_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_emergencies"
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    
    # Results
    successfully_rescheduled = models.PositiveIntegerField(default=0)
    failed_to_reschedule = models.PositiveIntegerField(default=0)
    
    initiated_by = models.ForeignKey("auth.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="initiated_emergencies")
    initiated_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
```

#### New Model: EmergencyRescheduleAudit

Immutable audit log of each individual appointment reschedule:

```python
class EmergencyRescheduleAudit(models.Model):
    emergency_action = models.ForeignKey(DoctorEmergencyAction, on_delete=models.CASCADE, related_name="reschedule_audits")
    appointment = models.ForeignKey(Appointment, on_delete=models.CASCADE, related_name="emergency_reschedule_audits")
    
    original_date = models.DateField()
    original_start_time = models.TimeField()
    original_end_time = models.TimeField()
    
    new_date = models.DateField()
    new_start_time = models.TimeField()
    new_end_time = models.TimeField()
    
    reschedule_sequence = models.PositiveSmallIntegerField()  # 1 (tomorrow), 2 (day-after), 3 (day-after-that)
    patient_notified = models.BooleanField(default=False)
    notification_method = models.CharField(
        max_length=20,
        choices=[("SMS", "SMS"), ("EMAIL", "Email"), ("IN_APP", "In-App"), ("NONE", "None")],
        default="IN_APP"
    )
    created_at = models.DateTimeField(auto_now_add=True)
```

#### Updated Model: AlertEvent

Extend to support receptionist approval alerts:

```python
class AlertEvent(models.Model):
    SEVERITY_CHOICES = [
        ("INFO", "Info"),
        ("WARN", "Warn"),
        ("CRITICAL", "Critical"),
    ]
    
    ALERT_TYPE_CHOICES = [
        ("CAPACITY_OVERFLOW", "Capacity Overflow"),
        ("PERFORMANCE", "Performance"),
        ("AUDIT", "Audit"),
        ("SYSTEM", "System"),
    ]
    
    alert_type = models.CharField(max_length=30, choices=ALERT_TYPE_CHOICES, default="SYSTEM")
    metric_name = models.CharField(max_length=100)
    observed_value = models.FloatField()
    threshold_value = models.FloatField()
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES)
    message = models.CharField(max_length=255)
    context = models.JSONField(default=dict)  # Can store emergency_action_id, etc.
    
    # For approval-required alerts
    requires_action = models.BooleanField(default=False)
    assigned_to = models.ForeignKey("auth.User", on_delete=models.SET_NULL, null=True, blank=True)
    action_taken = models.BooleanField(default=False)
    action_metadata = models.JSONField(default=dict)
    
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
```

---

### 2.2 Backend Services

#### New Service: `emergency_cancel_appointments_for_day()`

**Responsibility**: Orchestrate the entire emergency cancellation workflow.

```python
@transaction.atomic
def initiate_emergency_cancellation(doctor_id, today, reason, actor_username):
    """
    Phase 1: Validate and initiate emergency action.
    
    Returns:
    {
        'action_id': int,
        'total_appointments': int,
        'status': 'INITIATED' | 'CAPACITY_EXCEEDED',
        'approval_required': bool,
        'overflow_details': {
            'tomorrow_capacity': int,
            'appointments_to_reschedule': int,
            'excess_count': int,
        }
    }
    """
    doctor = Doctor.objects.select_for_update().get(id=doctor_id)
    today_appointments = Appointment.objects.filter(
        doctor=doctor,
        slot_date=today,
        status__in=['BOOKED', 'RESCHEDULED']
    )
    
    if not today_appointments.exists():
        raise ValueError("no_appointments_to_cancel")
    
    total_count = today_appointments.count()
    tomorrow = today + timedelta(days=1)
    
    # Check if tomorrow exists and has available capacity
    tomorrow_appointments = Appointment.objects.filter(
        doctor=doctor,
        slot_date=tomorrow,
        status__in=['BOOKED', 'RESCHEDULED']
    ).count()
    
    tomorrow_capacity = get_doctor_capacity_for_date(doctor, tomorrow)
    capacity_exceeded = (tomorrow_appointments + total_count) > tomorrow_capacity
    
    # Create emergency action record
    action = DoctorEmergencyAction.objects.create(
        doctor=doctor,
        action_date=today,
        total_appointments=total_count,
        status='INITIATED' if not capacity_exceeded else 'CAPACITY_EXCEEDED',
        reason=reason,
        tomorrow_available_slots=max(0, tomorrow_capacity - tomorrow_appointments),
        tomorrow_capacity=tomorrow_capacity,
        capacity_exceeded_by=max(0, (tomorrow_appointments + total_count) - tomorrow_capacity),
        approval_required=capacity_exceeded,
        initiated_by=User.objects.get(username=actor_username),
    )
    
    if capacity_exceeded:
        # Create alert for receptionist
        alert = AlertEvent.objects.create(
            alert_type='CAPACITY_OVERFLOW',
            metric_name=f'emergency_cancellation_{action.id}',
            observed_value=tomorrow_appointments + total_count,
            threshold_value=tomorrow_capacity,
            severity='CRITICAL',
            message=f"Dr. {doctor.full_name}'s emergency cancellation requires approval: "
                    f"{total_count} appointments to reschedule, only {tomorrow_capacity - tomorrow_appointments} slots available.",
            context={
                'emergency_action_id': action.id,
                'doctor_id': doctor_id,
                'action_date': str(today),
            },
            requires_action=True,
        )
        action.approval_required = True
        action.save(update_fields=['approval_required'])
    
    return {
        'action_id': action.id,
        'total_appointments': total_count,
        'status': action.status,
        'approval_required': action.approval_required,
        'overflow_details': {
            'tomorrow_capacity': tomorrow_capacity,
            'appointments_to_reschedule': total_count,
            'excess_count': action.capacity_exceeded_by,
        }
    }


@transaction.atomic
def approve_emergency_cancellation(action_id, approval_method, actor_username):
    """
    Phase 2: Receptionist approves the reschedule plan.
    
    approval_method: 'EXCEED' | 'DISTRIBUTE'
    """
    action = DoctorEmergencyAction.objects.select_for_update().get(id=action_id)
    
    if action.status not in ['INITIATED', 'CAPACITY_EXCEEDED']:
        raise ValueError("invalid_action_state")
    
    action.approval_method = approval_method
    action.approved_by = User.objects.get(username=actor_username)
    action.approved_at = timezone.now()
    action.status = 'APPROVED_EXCEED' if approval_method == 'EXCEED' else 'APPROVED_DISTRIBUTE'
    action.save()
    
    return {
        'action_id': action.id,
        'approval_method': approval_method,
        'ready_to_execute': True
    }


@transaction.atomic
def execute_emergency_reschedule(action_id):
    """
    Phase 3: Execute the bulk reschedule operation.
    
    - Mark appointments as RESCHEDULED
    - Create audit trail per appointment
    - Queue patient notifications
    - Handle failures gracefully (partial reschedule allowed)
    """
    action = DoctorEmergencyAction.objects.select_for_update().get(id=action_id)
    
    if action.status not in ['INITIATED', 'APPROVED_EXCEED', 'APPROVED_DISTRIBUTE']:
        raise ValueError("invalid_action_state")
    
    action.status = 'IN_PROGRESS'
    action.save(update_fields=['status'])
    
    today_appointments = Appointment.objects.select_for_update().filter(
        doctor=action.doctor,
        slot_date=action.action_date,
        status__in=['BOOKED', 'RESCHEDULED']
    ).order_by('start_time')
    
    successfully_rescheduled = 0
    failed_count = 0
    sequence = 1  # Day offset: 1=tomorrow, 2=day-after, etc.
    max_sequence = 3  # Try up to 3 days ahead
    
    for appointment in today_appointments:
        rescheduled = False
        original_date = appointment.slot_date
        original_start = appointment.start_time
        original_end = appointment.end_time
        
        # Try sequence of days
        for attempt_seq in range(1, max_sequence + 1):
            target_date = original_date + timedelta(days=attempt_seq)
            
            # Check if doctor works on target_date
            if not _doctor_works_on_date(action.doctor, target_date):
                continue
            
            # For DISTRIBUTE mode: check capacity constraint
            if action.approval_method == 'DISTRIBUTE':
                current_count = Appointment.objects.filter(
                    doctor=action.doctor,
                    slot_date=target_date,
                    status__in=['BOOKED', 'RESCHEDULED']
                ).count()
                capacity = get_doctor_capacity_for_date(action.doctor, target_date)
                if current_count >= capacity:
                    continue
            
            # Try to find slot at same time on target_date
            slot = _get_available_slot(action.doctor.id, target_date, original_start)
            if not slot:
                # Try first available slot on that day
                slot = DoctorSlot.objects.filter(
                    doctor=action.doctor,
                    slot_date=target_date,
                    status='AVAILABLE'
                ).order_by('start_time').first()
            
            if slot:
                # Reschedule appointment
                appointment.slot_date = target_date
                appointment.start_time = slot.start_time
                appointment.end_time = slot.end_time
                appointment.status = 'RESCHEDULED'
                appointment.rescheduled_due_to_emergency = True
                appointment.original_slot_date = original_date
                appointment.original_start_time = original_start
                appointment.original_end_time = original_end
                appointment.reschedule_reason = 'EMERGENCY_DOCTOR'
                appointment.rescheduled_at = timezone.now()
                appointment.rescheduled_by = action.initiated_by
                appointment.save()
                
                # Audit trail
                EmergencyRescheduleAudit.objects.create(
                    emergency_action=action,
                    appointment=appointment,
                    original_date=original_date,
                    original_start_time=original_start,
                    original_end_time=original_end,
                    new_date=target_date,
                    new_start_time=slot.start_time,
                    new_end_time=slot.end_time,
                    reschedule_sequence=attempt_seq,
                    patient_notified=False,
                )
                
                # Log event
                AppointmentEvent.objects.create(
                    appointment=appointment,
                    action='RESCHEDULE',
                    previous_status='BOOKED',
                    new_status='RESCHEDULED',
                    reason=f'Emergency doctor unavailability (bulk reschedule action {action.id})',
                    actor_username='system',
                )
                
                successfully_rescheduled += 1
                rescheduled = True
                break
        
        if not rescheduled:
            failed_count += 1
    
    action.successfully_rescheduled = successfully_rescheduled
    action.failed_to_reschedule = failed_count
    action.status = 'COMPLETED' if failed_count == 0 else 'FAILED'
    action.completed_at = timezone.now()
    action.save()
    
    return {
        'action_id': action.id,
        'total': action.total_appointments,
        'successful': successfully_rescheduled,
        'failed': failed_count,
        'status': action.status,
    }
```

#### Helper Service: Notification Queue

```python
def queue_patient_notifications(action_id):
    """
    Queue SMS/in-app notifications for all rescheduled patients.
    This should be async (Celery task).
    """
    action = DoctorEmergencyAction.objects.get(id=action_id)
    audits = EmergencyRescheduleAudit.objects.filter(
        emergency_action=action,
        patient_notified=False
    )
    
    for audit in audits:
        appointment = audit.appointment
        patient = appointment.patient
        
        message = (
            f"Your appointment with Dr. {appointment.doctor.display_name} "
            f"originally scheduled for {audit.original_date} has been rescheduled "
            f"to {audit.new_date} at {audit.new_start_time.strftime('%I:%M %p')}. "
            f"Please confirm your attendance."
        )
        
        # Send SMS if phone available
        if patient.phone:
            try:
                send_sms(patient.phone, message)
                audit.notification_method = 'SMS'
            except Exception as e:
                audit.notification_method = 'IN_APP'
        else:
            audit.notification_method = 'IN_APP'
        
        # Create in-app notification
        create_notification(
            user=patient,
            type='APPOINTMENT_RESCHEDULED',
            title='Appointment Rescheduled',
            message=message,
            metadata={'appointment_id': appointment.id}
        )
        
        audit.patient_notified = True
        audit.save(update_fields=['patient_notified', 'notification_method'])
```

---

### 2.3 Frontend Components

#### Doctor Emergency Cancel UI

**Location**: `frontend/src/features/appointments/EmergencyDoctorCancel.tsx`

**Flow**:
1. Doctor clicks "Cancel All Today's Appointments" button (in doctor dashboard)
2. Confirmation modal asks: "Are you sure? This will reschedule all [N] appointments."
3. Text input for reason (medical emergency, personal emergency, etc.)
4. Submit → API call to `initiate_emergency_cancellation()`
5. **Case A**: No capacity issues → Proceed directly to execution
6. **Case B**: Capacity exceeded → Show waiting screen, poll for receptionist approval

**Key Features**:
- Real-time progress indicator during reschedule
- Show summary: "X successfully rescheduled, Y still waiting for slots"
- List affected patients and their new appointment times
- Abort option (cancels entire operation if in-progress)

#### Receptionist Approval UI

**Location**: `frontend/src/features/alerts/CapacityOverflowApproval.tsx`

**Flow**:
1. Alert badge appears on receptionist dashboard ("⚠️ Dr. [Name] - Approval Needed")
2. Click to open approval modal showing:
   - Doctor name, action date
   - Number of appointments to reschedule
   - Current tomorrow capacity (used/total)
   - Appointments exceeding capacity: **X**
3. Two buttons:
   - "Approve & Exceed Capacity" → allows tomorrow to go over limit
   - "Move Excess to Next Days" → distributes overflow to following days
4. Optional note field
5. Submit → logs approval, returns control to doctor interface

---

## 3. IMPLEMENTATION COMPLEXITY

### Complexity Breakdown

| Component | Complexity | Effort | Dependencies |
|-----------|-----------|--------|--------------|
| **Database Schema** | Low | 2-3 hours | Django migrations |
| **Core Reschedule Logic** | HIGH | 8-12 hours | Transaction handling, slot validation |
| **Capacity Checking** | Medium | 4-5 hours | Schedule template queries |
| **Receptionist Approval Flow** | Medium | 6-8 hours | AlertEvent, user assignment, WebSocket for real-time |
| **Patient Notifications** | Medium | 5-7 hours | SMS gateway, async tasks (Celery) |
| **Audit Trail** | Low | 3-4 hours | Event logging, immutable records |
| **Doctor Emergency UI** | Medium | 6-8 hours | Modal, progress tracking, real-time updates |
| **Receptionist Alert UI** | Medium | 5-6 hours | Dashboard integration, badge system |
| **End-to-End Testing** | HIGH | 10-15 hours | Fixtures, edge cases, race conditions |
| **Documentation** | Low | 2-3 hours | Runbooks, API docs |
| **TOTAL ESTIMATE** | **HIGH** | **51-71 hours** | ~2-3 weeks sprint |

### Key Complexities

1. **Transaction Atomicity**
   - All-or-nothing semantics needed; partial reschedules can leave data inconsistent
   - Must handle deadlock/race conditions (multiple doctors cancelling simultaneously)
   - Solution: Use `select_for_update()` on doctor, appointments, and emergency action records

2. **Capacity Overflow Handling**
   - Multi-step approval workflow has state that can expire or fail
   - Must prevent race condition: receptionist approves, but new bookings fill slots before reschedule executes
   - Solution: Lock slots during approval window, or accept "best-effort" rescheduling

3. **Slot Availability Discovery**
   - Finding "best" available slots across multiple days is O(n*m) complexity
   - Must handle:
     - Different schedule on different days of week
     - Break times, doctor leaves
     - Prefer same time slot, fallback to any available
   - Solution: Pre-generate slots, use indexed queries

4. **Patient Notification Timing**
   - Notifications must be SENT AFTER reschedule is COMMITTED
   - Cannot fail reschedule due to SMS gateway failure
   - Solution: Async notification task (Celery), audit trail shows notification status

5. **Queue Item Synchronization**
   - When appointment is rescheduled, related QueueItem must also be updated
   - Current queue on today's date becomes invalid
   - Solution: Cascade updates from Appointment → QueueItem, sync queue for new date

6. **Audit Trail Completeness**
   - Must track: who did what, when, why, old values, new values
   - Multiple events created: DoctorEmergencyAction, Appointment updates, EmergencyRescheduleAudit
   - Solution: Immutable audit models, use transaction hooks

---

## 4. ARCHITECTURE DESIGN

### 4.1 High-Level Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                     Doctor Interface                             │
│  "Cancel All Today's Appointments" Button                        │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│         [1] initiate_emergency_cancellation()                    │
│      - Validate doctor exists & has appointments for today       │
│      - Check tomorrow's capacity                                 │
│      - Create DoctorEmergencyAction record (status: INITIATED)   │
│      - Return: needs_approval (bool)                             │
└────────────────────────┬────────────────────────────────────────┘
                         │
                  ┌──────┴──────┐
                  │             │
              No Overflow    Overflow
                  │             │
                  ▼             ▼
          ┌──────────────┐ ┌──────────────────────┐
          │   Auto-OK    │ │  Receptionist Alert  │
          │   Proceed    │ │  "Approve & Exceed"  │
          │              │ │  "Distribute Excess" │
          └──────┬───────┘ └──────────┬───────────┘
                 │                    │
                 └────────┬───────────┘
                          │
                          ▼
            ┌──────────────────────────────────────┐
            │ [2] execute_emergency_reschedule()   │
            │  - For each appointment today:       │
            │    - Try tomorrow (same slot time)   │
            │    - Fallback: next available        │
            │    - Respect capacity constraints    │
            │  - Create Appointment event          │
            │  - Create EmergencyRescheduleAudit   │
            │  - Update appointment to RESCHEDULED │
            │  - Queue patient notifications       │
            └──────────────┬───────────────────────┘
                           │
                           ▼
            ┌──────────────────────────────────────┐
            │ [3] queue_patient_notifications()    │
            │  - SMS (if phone exists)             │
            │  - In-app notification               │
            │  - Async task (Celery)               │
            │  - Mark audit as notified            │
            └──────────────┬───────────────────────┘
                           │
                           ▼
                   ┌────────────────┐
                   │   Success      │
                   │  Page Summary  │
                   └────────────────┘
```

### 4.2 Database Transaction Flow

**Phase 1: Initiation**
```
START TRANSACTION
  1. SELECT doctor FOR UPDATE
  2. SELECT appointments for today FOR UPDATE
  3. SELECT appointments for tomorrow (read-only)
  4. INSERT DoctorEmergencyAction
  5. IF capacity_exceeded:
       INSERT AlertEvent (requires_action=true)
COMMIT
```

**Phase 2: Approval** (Receptionist)
```
START TRANSACTION
  1. SELECT DoctorEmergencyAction FOR UPDATE
  2. UPDATE status → APPROVED_*
  3. UPDATE approved_by, approval_method, approved_at
COMMIT
```

**Phase 3: Execution** (Bulk reschedule)
```
START TRANSACTION
  1. SELECT DoctorEmergencyAction FOR UPDATE
  2. SELECT appointments for today FOR UPDATE (ORDER BY start_time)
  3. FOR EACH appointment:
       a. SELECT available slots for target date FOR UPDATE
       b. UPDATE appointment (new slot_date, start_time, end_time, status=RESCHEDULED)
       c. INSERT AppointmentEvent
       d. INSERT EmergencyRescheduleAudit
       e. SELECT QueueItem, UPDATE if exists
       f. CALL sync_queue_for_day for new date
  4. UPDATE DoctorEmergencyAction (status=COMPLETED, counts)
  5. UPDATE AlertEvent (action_taken=true)
COMMIT
```

### 4.3 Service Layer Architecture

```
services.py (existing)
├── initiate_emergency_cancellation()
│   ├── _validate_doctor_exists()
│   ├── _get_today_appointments()
│   ├── _calculate_tomorrow_capacity()
│   └── _create_emergency_action()
│
├── approve_emergency_cancellation()
│   ├── _validate_action_state()
│   └── _update_action_status()
│
├── execute_emergency_reschedule()
│   ├── _doctor_works_on_date()
│   ├── _find_best_available_slot()
│   ├── _reschedule_single_appointment()
│   └── _sync_queue_items()
│
└── queue_patient_notifications()
    ├── _send_sms()
    ├── _create_in_app_notification()
    └── _record_notification_audit()
```

### 4.4 API Endpoints

**POST** `/api/v1/appointments/emergency-cancel/initiate/`
```json
{
  "doctor_id": 5,
  "reason": "Medical emergency - family health issue",
  "action_date": "2026-05-09"
}

Response (200):
{
  "action_id": 42,
  "total_appointments": 8,
  "status": "CAPACITY_EXCEEDED",
  "approval_required": true,
  "overflow_details": {
    "tomorrow_capacity": 50,
    "appointments_to_reschedule": 8,
    "excess_count": 3
  }
}
```

**POST** `/api/v1/appointments/emergency-cancel/approve/`
```json
{
  "action_id": 42,
  "approval_method": "DISTRIBUTE",
  "note": "Moving excess to day-after-tomorrow"
}

Response (200):
{
  "action_id": 42,
  "status": "APPROVED_DISTRIBUTE",
  "ready_to_execute": true
}
```

**POST** `/api/v1/appointments/emergency-cancel/execute/`
```json
{
  "action_id": 42
}

Response (200 - async):
{
  "action_id": 42,
  "status": "IN_PROGRESS",
  "task_id": "celery-task-uuid"
}

# Later, poll:
GET /api/v1/appointments/emergency-cancel/status/42/

Response (200):
{
  "action_id": 42,
  "status": "COMPLETED",
  "total": 8,
  "successful": 8,
  "failed": 0,
  "rescheduled_appointments": [
    {
      "appointment_id": 101,
      "patient_name": "John Doe",
      "original_date": "2026-05-09",
      "new_date": "2026-05-10",
      "new_time": "10:00-10:15"
    },
    ...
  ]
}
```

---

## 5. RISKS & EDGE CASES

### 5.1 Data Consistency Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|-----------|
| **Partial reschedule** (some appointments fail) | Medium | Patient confusion, data inconsistency | Accept as "best-effort", show summary, manual follow-up |
| **Slot race condition** (slot fills between check & reschedule) | High | Reschedule fails for some appts | Use database-level SELECT FOR UPDATE locking |
| **Queue sync failure** (QueueItem not updated when appt moves) | Medium | Queue becomes stale for today's slot | Cascade updates in transaction, rebuild queue on day boundary |
| **SMS gateway timeout** (patient not notified) | Low | Patient doesn't know reschedule date | Retry async notifications, show "pending notification" flag |
| **Doctor cancels while receptionist approving** | Low | Orphaned alert record | Use state machine, reject operations on non-active states |

### 5.2 Business Logic Edge Cases

| Edge Case | Behavior | Implementation |
|-----------|----------|-----------------|
| **No appointments today** | Error: "No appointments to cancel" | Validate in initiate phase |
| **Doctor works only Mon-Fri, emergency on Friday** | Reschedule to Monday (skip weekend) | Use DoctorScheduleTemplate to check day-of-week |
| **Tomorrow is doctor's leave day** | Skip to next working day | Query DoctorSlot status, check for blocked slots |
| **All future 3 days are fully booked** | Mark appointments as "PENDING_RESCHEDULE", manual intervention | Return failed appointments, alert clinic admin |
| **Patient has emergency too (cancels own appointment)** | Can cancel independently before bulk reschedule starts | Last-write-wins: if patient cancels before system reschedules, mark as CANCELLED |
| **Appointment already in consultation** | Cannot reschedule if doctor is with patient | Check Consultation.status == 'DRAFT' before reschedule |
| **Receptionist doesn't approve in 30 mins** | Auto-escalate to clinic manager/admin | Scheduled task to check AlertEvent age, re-assign |
| **Receptionist chooses "Distribute", but capacity still exceeded** | Cascade to day-after-that, repeat until slots found (3-day window) | Loop in execute phase, gracefully fail if no slots |

### 5.3 Concurrency Risks

| Scenario | Risk Level | Solution |
|----------|-----------|----------|
| Two doctors simultaneously cancel (same clinic) | Medium | SELECT FOR UPDATE on Doctor, Appointment tables; queue serializes |
| Receptionist approving while doctor aborts cancellation | Low | Check action.status in execute phase, reject if CANCELLED |
| New appointments booked during reschedule | High | Lock target date's slots during execution, or accept overages |
| Multiple receptionist approvals of same action | Low | Check approval_by field; already approved is idempotent |

### 5.4 Clinic Operations Edge Cases

| Scenario | Behavior |
|----------|----------|
| **Doctor has 60 appointments today, only 50-slot capacity for tomorrow** | Receptionist must choose: exceed capacity or spread over 2-3 days. Manual resolution if weekend blocks days. |
| **Patient calls to confirm reschedule, but SMS failed** | In-app notification shows status; receptionist can manually verify or resend SMS |
| **Doctor changes mind after approval, wants to work today anyway** | System allows marking appointments back to BOOKED manually, but audit trail shows cancellation attempt. |
| **New doctor hire, no schedule template yet** | emergency_cancellation should fail gracefully ("Doctor has no schedule defined") |

---

## 6. WORKFLOW DIAGRAMS

### 6.1 Doctor Emergency Cancellation Flow

```
Doctor Dashboard
    │
    ├─► Click "Cancel All Today's Appointments"
    │
    ▼
Confirmation Modal
    ├─ "Are you sure? [N] appointments affected"
    ├─ Text input: "Reason for cancellation"
    ├─ [Cancel] [Proceed]
    │
    └─► [Proceed] ─────────────────────────┐
                                            │
                                            ▼
                          API: initiate_emergency_cancellation()
                                            │
                   ┌────────────────────────┼────────────────────────┐
                   │                        │                        │
                   ▼                        ▼                        ▼
            ERROR: No appts      INITIATED: No overflow    CAPACITY_EXCEEDED
                   │             (auto proceed)            (await approval)
                   │                        │                        │
                   │                        ▼                        ▼
                   │              Waiting Screen:        Receptionist Alert
                   │              "Processing..."        Dashboard Badge
                   │              [Abort]                "[N] appts need approval"
                   │                        │            [Tap to Review]
                   │                        │                        │
                   │                        │                        ▼
                   │                        │            Approval Modal
                   │                        │            ├─ [Exceed Capacity]
                   │                        │            └─ [Distribute]
                   │                        │                        │
                   │                        └────────────┬───────────┘
                   │                                     │
                   ▼                                     ▼
              Error Toast                 execute_emergency_reschedule()
           "Cancelled by user                           │
            or reschedule failed"               ┌───────┴───────┐
                   │                            │               │
                   │                      SUCCESS         PARTIAL FAIL
                   │                      (8/8)           (6/8 moved)
                   │                            │               │
                   └────────────────┬───────────┴───────────────┘
                                    │
                                    ▼
                          Completion Summary
                          ├─ "Successfully rescheduled: [N]"
                          ├─ Table: [Patient | Old Date | New Date/Time]
                          └─ [Done] [Print List] [Email Report]
```

### 6.2 Receptionist Approval Decision Flow

```
DoctorEmergencyAction Created
    Status: CAPACITY_EXCEEDED
    Capacity Exceeded By: 3 appointments
                    │
                    ▼
        AlertEvent (CRITICAL)
        ├─ Assigned to: Receptionist Group
        ├─ Context: {doctor_id, action_date, excess_count}
        │
        ▼
Receptionist Dashboard
    Badge: "⚠️ Dr. Sharma - Approval Needed"
    │
    ├─► Click Badge ─────────────────────────────┐
    │                                             │
    ▼                                             ▼
Modal: Emergency Reschedule Approval      (OR: Review Later)
    ├─ Dr. Sharma cancelled: 8 appointments
    ├─ Action Date: May 9, 2026
    ├─ Tomorrow (May 10) Capacity:
    │   ├─ Current booked: 47
    │   ├─ Daily capacity: 50
    │   ├─ Attempting reschedule: +8 = 55 (5 over limit)
    │
    ├─ [Option A]
    │  Approve & Exceed Capacity
    │  └─ Risk: May hurt clinical quality/wait times
    │
    ├─ [Option B]
    │  Move Excess to Following Days
    │  └─ 5 appointments to May 11, rest to May 12, etc.
    │
    ├─ [Optional Note Field]
    │
    └─ [Cancel] [Approve & Exceed] [Move Excess]
                    │                    │
                    ▼                    ▼
            Approval saved         Approval saved
            approval_method:       approval_method:
            EXCEED                 DISTRIBUTE
                    │                    │
                    └────────┬───────────┘
                             │
                             ▼
              Alert resolves, execute proceeds
```

### 6.3 Patient Notification Flow

```
Appointment Rescheduled
    (new date: May 10)
                │
                ▼
        EmergencyRescheduleAudit
        ├─ original_date: May 9
        ├─ new_date: May 10
        ├─ patient_notified: FALSE
                │
                ▼
    Async Task: queue_patient_notifications()
        │
        ├─ Check patient.phone
        │
        ├─► [Has Phone]
        │   ├─ Build SMS message
        │   ├─ Attempt send_sms()
        │   │  ├─► Success: notification_method = SMS
        │   │  └─► Fail: notification_method = IN_APP (retry later)
        │   │
        │   ├─ Create in-app notification
        │   └─ patient_notified = TRUE
        │
        └─► [No Phone]
            ├─ Create in-app notification only
            └─ patient_notified = TRUE
```

---

## 7. ESTIMATED EFFORT & BREAKDOWN

### 7.1 Implementation Timeline (2-3 Week Sprint)

| Phase | Task | Effort | Days | Owner |
|-------|------|--------|------|-------|
| **ANALYSIS** | Clarify remaining requirements, finalize data model | 4h | 0.5 | PM + Architect |
| **DATABASE** | Create migrations for new models, indexes | 4h | 0.5 | Backend |
| **BACKEND** | Implement core services (initiate, approve, execute) | 20h | 2.5 | Backend |
| **BACKEND** | Implement notification service + Celery tasks | 8h | 1 | Backend |
| **BACKEND** | API endpoints + error handling | 6h | 0.75 | Backend |
| **BACKEND** | Unit tests + integration tests | 12h | 1.5 | Backend + QA |
| **FRONTEND** | Emergency cancel modal + confirmation UX | 8h | 1 | Frontend |
| **FRONTEND** | Receptionist approval alert + decision modal | 6h | 0.75 | Frontend |
| **FRONTEND** | Completion summary + result display | 4h | 0.5 | Frontend |
| **FRONTEND** | Real-time progress tracking (WebSocket) | 6h | 0.75 | Frontend |
| **FRONTEND** | UI tests + E2E scenarios | 8h | 1 | Frontend + QA |
| **DOCUMENTATION** | API docs, runbooks, on-call guide | 4h | 0.5 | Tech Writer |
| **QA** | Manual testing all workflows, edge cases | 16h | 2 | QA |
| **CONTINGENCY** | Unforeseen issues, refactoring | 8h | 1 | All |
| **TOTAL** | | **114h** | **14 days** | |

### 7.2 Priority Breakdown

**Must-Have (MVP - Week 1)**
- Emergency cancellation initiation
- Basic reschedule to next available day
- Audit trail logging
- Patient notification (SMS + in-app)
- Doctor confirmation UI

**Should-Have (Phase 1 - Week 2)**
- Receptionist capacity approval workflow
- Multi-day distribution logic
- Real-time progress tracking
- Comprehensive testing

**Nice-to-Have (Phase 2 - Future)**
- Doctor unavailability (date range) feature
- Advanced analytics (cancellation frequency by reason)
- Automated escalation workflow
- Email notifications
- Integration with doctor's calendar app

---

## 8. RECOMMENDATIONS

### 8.1 Phased Approach

**Phase 0 (Immediate - 1-2 days)**
- Finalize business rules with clinic stakeholders
- Get sign-off on capacity handling rules
- Document edge case resolutions

**Phase 1 (MVP - 1.5 weeks)**
- Core emergency cancellation + auto-reschedule
- No receptionist approval (auto-proceed even if capacity exceeded)
- Basic in-app notifications
- Audit trail and reporting
- **Deploy to staging**, user acceptance testing

**Phase 2 (1 week)**
- Add receptionist approval workflow
- Multi-day distribution logic
- SMS notifications via gateway
- Advanced testing
- **Deploy to production**

**Phase 3 (Optional - future)**
- Doctor unavailability range
- Email notifications
- Calendar integrations

### 8.2 Risk Mitigation Strategies

| Risk | Mitigation |
|------|-----------|
| **Data inconsistency** | 100% transaction atomicity (select_for_update), never partial commits |
| **Slot race conditions** | Lock slots during approval & execution windows, show "may not reschedule" warnings |
| **SMS delivery failures** | Async retry logic, in-app notification fallback, manual verification UI |
| **Receptionist delays** | 30-min auto-escalation alert, fallback to auto-exceed (with approval_required flag) |
| **Queue sync bugs** | Comprehensive testing with concurrent operations, queue rebuild at day boundary |

### 8.3 Key Success Metrics

- **Reschedule Success Rate**: > 95% of appointments rescheduled within 3-day window
- **Patient Notification Delivery**: > 90% notified within 5 minutes of reschedule
- **Receptionist Response Time**: < 30 min average approval latency
- **System Performance**: Bulk reschedule of 50+ appointments < 10 seconds
- **Data Integrity**: 100% audit trail completeness, zero orphaned records

### 8.4 Technical Debt & Future Improvements

1. **Slot Pre-allocation**: Cache available slots per day to avoid O(n*m) discovery
2. **Async Execution**: Move reschedule execution to background task (Celery) for UX
3. **Doctor Preferences**: Allow doctors to prefer certain rescheduling patterns
4. **Analytics Dashboard**: Track cancellation frequency, reasons, failure patterns
5. **Integration**: Sync with doctor's personal calendar (Google Cal, Outlook)

---

## 9. IMPLEMENTATION CHECKLIST

- [ ] Requirements finalized with stakeholders
- [ ] Data model approved & reviewed
- [ ] Database migrations created & tested
- [ ] Core service functions implemented
- [ ] API endpoints designed & documented
- [ ] Doctor emergency cancel UI built
- [ ] Receptionist approval UI built
- [ ] Patient notification system integrated
- [ ] Comprehensive unit tests written
- [ ] Integration tests for full workflows
- [ ] E2E tests (doctor → approval → reschedule → notification)
- [ ] Load testing (bulk reschedule of 100+ appointments)
- [ ] Staging deployment & UAT
- [ ] Documentation updated (API, runbooks, on-call)
- [ ] Production rollout plan (feature flag)
- [ ] Monitoring & alerting configured
- [ ] Post-launch review & optimization

---

## 10. QUESTIONS FOR CLARIFICATION

Before implementation, get stakeholder sign-off on:

1. **What's the maximum number of consecutive days to attempt rescheduling?** (Recommended: 3 days)
2. **If all 3 days are full, should we auto-cancel the appointments or mark them for manual intervention?** (Recommend: Mark PENDING_RESCHEDULE, alert clinic admin)
3. **Can a doctor cancel their own emergency action if they change their mind mid-reschedule?** (Recommend: Yes, if status is not COMPLETED)
4. **Should we notify the doctor with a summary report after completion?** (Recommend: Yes, email + in-app)
5. **Are there any specific local regulations (India/Maharashtra) about rescheduling appointments?** (Assume: No legal constraints, but note for compliance audit)

---

**Document Owner**: AI Architecture Team  
**Last Updated**: May 9, 2026  
**Next Review**: Upon requirement clarification completion
