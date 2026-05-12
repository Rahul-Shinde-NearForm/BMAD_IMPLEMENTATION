# OPD Management System - Codebase Exploration Summary

**Date**: May 9, 2026  
**Focus**: Appointment and Consultation Workflow

---

## 1. APPOINTMENT MODEL DEFINITION

**Location**: `backend/apps/core/models.py` (Lines 106-159)

### Complete Model Code
```python
class Appointment(models.Model):
	STATUS_CHOICES = [
		("BOOKED", "Booked"),
		("RESCHEDULED", "Rescheduled"),
		("COMPLETED", "Completed"),
		("CANCELLED", "Cancelled"),
	]

	VISIT_TYPE_CHOICES = [
		("NEW", "New"),
		("FOLLOW_UP", "Follow Up"),
	]

	CHANNEL_CHOICES = [
		("WALK_IN", "Walk-In"),
		("ONLINE", "Online"),
		("PHONE", "Phone"),
	]

	patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="appointments")
	doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE, related_name="appointments")
	slot_date = models.DateField()
	start_time = models.TimeField()
	end_time = models.TimeField()
	visit_type = models.CharField(max_length=20, choices=VISIT_TYPE_CHOICES, default="NEW")
	channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES, default="WALK_IN")
	opd_number = models.CharField(max_length=30, unique=True, null=True, blank=True)
	status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="BOOKED")
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["-created_at"]

	def save(self, *args, **kwargs):
		new_record = self.pk is None
		super().save(*args, **kwargs)
		if new_record and not self.opd_number:
			self.opd_number = f"OPD-{self.pk:08d}"
			super().save(update_fields=["opd_number"])
```

### Appointment Status Field Options
- **BOOKED**: Initial status when appointment is created
- **RESCHEDULED**: Status after rescheduling appointment
- **COMPLETED**: Status after doctor completes the visit
- **CANCELLED**: Status when appointment is cancelled

### Key Relationships
- `patient` → Links to Patient model (one-to-many)
- `doctor` → Links to Doctor model (one-to-many)
- `slot_date` → Date of the appointment
- `start_time` & `end_time` → Time slot boundaries
- `visit_type` → NEW or FOLLOW_UP
- `channel` → WALK_IN, ONLINE, or PHONE

---

## 2. CONSULTATION MODEL DEFINITION

**Location**: `backend/apps/core/models.py` (Lines 184-217)

### Complete Model Code
```python
class Consultation(models.Model):
	STATUS_CHOICES = [
		("DRAFT", "Draft"),
		("FINALIZED", "Finalized"),
	]

	appointment = models.OneToOneField(Appointment, on_delete=models.CASCADE, related_name="consultation")
	doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE, related_name="consultations")
	patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="consultations")
	chief_complaint = models.TextField(blank=True, default="")
	findings = models.TextField(blank=True, default="")
	diagnosis = models.TextField(blank=True, default="")
	notes = models.TextField(blank=True, default="")
	follow_up_date = models.DateField(null=True, blank=True)
	status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="DRAFT")
	finalized_by = models.CharField(max_length=150, blank=True, default="")
	finalized_at = models.DateTimeField(null=True, blank=True)
	created_by = models.CharField(max_length=150)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["-created_at"]
```

### Consultation Status Field Options
- **DRAFT**: Initial status when consultation is created; editable
- **FINALIZED**: Status when doctor finalizes the consultation; locks editing

### Key Fields & Relationships
- `appointment` → One-to-one link to Appointment (each appointment has one consultation)
- `doctor` → FK to Doctor who conducted consultation
- `patient` → FK to Patient being consulted
- `chief_complaint` → C/O text input
- `findings` → Clinical findings documented by doctor
- `diagnosis` → Diagnosis details
- `notes` → Additional notes/instructions
- `follow_up_date` → Scheduled follow-up date (nullable)
- `finalized_by` → Username of doctor who finalized
- `finalized_at` → Timestamp when consultation was finalized
- `created_by` → Username of doctor who created consultation

---

## 3. QUEUE ITEM MODEL

**Location**: `backend/apps/core/models.py` (Lines 310-332)

### Queue Item Status Options
```python
class QueueItem(models.Model):
	STATUS_CHOICES = [
		("WAITING", "Waiting"),
		("CALLED", "Called"),
		("SKIPPED", "Skipped"),
		("COMPLETED", "Completed"),
		("NO_SHOW", "No Show"),
	]

	appointment = models.OneToOneField(Appointment, on_delete=models.CASCADE, related_name="queue_item")
	doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE, related_name="queue_items")
	slot_date = models.DateField()
	token_number = models.PositiveIntegerField()
	status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="WAITING")
	called_at = models.DateTimeField(null=True, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["slot_date", "token_number"]
		unique_together = ("doctor", "slot_date", "token_number")
```

---

## 4. APPOINTMENT STATE TRANSITION MATRIX

**Location**: `backend/apps/core/services.py` (Lines 47-53)

```python
APPOINTMENT_TRANSITIONS = {
    "BOOKED": {"RESCHEDULED", "COMPLETED", "CANCELLED"},
    "RESCHEDULED": {"RESCHEDULED", "COMPLETED", "CANCELLED"},
    "COMPLETED": set(),
    "CANCELLED": set(),
}
```

### Valid Transitions
- **BOOKED** → RESCHEDULED, COMPLETED, CANCELLED
- **RESCHEDULED** → RESCHEDULED (again), COMPLETED, CANCELLED
- **COMPLETED** → No further transitions (terminal state)
- **CANCELLED** → No further transitions (terminal state)

---

## 5. QUEUE STATE TRANSITION MATRIX

**Location**: `backend/apps/core/services.py` (Lines 55-60)

```python
QUEUE_TRANSITIONS = {
    "WAITING": {"SKIPPED", "NO_SHOW", "COMPLETED", "CALLED"},
    "CALLED": {"SKIPPED", "NO_SHOW", "COMPLETED"},
    "SKIPPED": {"CALLED", "NO_SHOW", "COMPLETED"},
    "COMPLETED": set(),
    "NO_SHOW": set(),
}
```

### Valid Queue Transitions
- **WAITING** → SKIPPED, NO_SHOW, COMPLETED, CALLED
- **CALLED** → SKIPPED, NO_SHOW, COMPLETED (can transition to SKIPPED but not back to WAITING)
- **SKIPPED** → CALLED (recall), NO_SHOW, COMPLETED
- **COMPLETED** → No transitions (terminal)
- **NO_SHOW** → No transitions (terminal)

---

## 6. VIEW FUNCTIONS - APPOINTMENT LISTING

**Location**: `backend/apps/core/views.py`

### 6.1 Doctor Today Appointments View
**Lines**: 938-1008  
**Route**: `GET /api/appointments/today/`  
**Decorators**: `@require_GET`, `@login_required`, `@role_required("Doctor", "Admin")`

```python
@login_required(login_url="/login/")
@role_required("Doctor", "Admin")
def doctor_today_appointments(request):
	from django.utils import timezone
	from datetime import timedelta

	doctor, doctor_ids = _resolve_doctor_scope_for_user(request.user)
	if not doctor or not doctor_ids:
		return JsonResponse({
			"doctor_id": None,
			"doctor_name": request.user.first_name or request.user.username,
			"date": str(timezone.localdate()),
			"latest_called_appointment_id": None,
			"appointments": [],
		})
	
	# Get date based on date_type parameter (today or tomorrow)
	date_type = request.GET.get("date_type", "today")
	for_date = timezone.localdate()
	if date_type == "tomorrow":
		for_date = for_date + timedelta(days=1)

	for doctor_id in doctor_ids:
		sync_queue_for_day(doctor_id, for_date)
	
	queue_items = {
		item.appointment_id: item
		for item in QueueItem.objects.filter(doctor_id__in=doctor_ids, slot_date=for_date)
	}
	
	latest_called = (
		QueueItem.objects
		.filter(doctor_id__in=doctor_ids, slot_date=for_date, status="CALLED")
		.order_by("-called_at")
		.first()
	)
	
	appointments = (
		Appointment.objects
		.select_related("patient", "doctor")
		.filter(doctor_id__in=doctor_ids, slot_date=for_date)
		.exclude(status="CANCELLED")
		.order_by("start_time")
	)
	
	return JsonResponse({
		"doctor_id": doctor.id,
		"doctor_name": doctor.display_name,
		"date": str(for_date),
		"latest_called_appointment_id": latest_called.appointment_id if latest_called else None,
		"appointments": [
			{
				"appointment_id": a.id,
				"opd_number": a.opd_number,
				"patient_id": a.patient_id,
				"patient_name": f"{a.patient.first_name} {a.patient.last_name}",
				"mobile": a.patient.phone,
				"start_time": a.start_time.strftime("%H:%M"),
				"end_time": a.end_time.strftime("%H:%M"),
				"status": a.status,
				"queue_token": queue_items[a.id].token_number if a.id in queue_items else None,
				"queue_status": queue_items[a.id].status if a.id in queue_items else "NOT_IN_QUEUE",
			}
			for a in appointments
		],
	})
```

**Key Features**:
- Returns today's or tomorrow's appointments for the logged-in doctor
- Syncs queue for the date (auto-creates QueueItems for BOOKED/RESCHEDULED appointments)
- Tracks latest called appointment
- Orders appointments by `start_time`
- Returns queue token and status for each appointment
- Excludes CANCELLED appointments

---

### 6.2 Receptionist Today Appointments Board
**Lines**: 1011-1054  
**Route**: `GET /api/appointments/board/today/`  
**Decorators**: `@require_GET`, `@login_required`, `@role_required("Receptionist", "Admin")`

```python
@require_GET
@login_required
@role_required("Receptionist", "Admin")
def receptionist_today_appointments_board(request):
	from django.utils import timezone

	for_date = timezone.localdate()
	doctor_ids = list(
		Doctor.objects.filter(appointments__slot_date=for_date)
		.distinct()
		.values_list("id", flat=True)
	)
	for doctor_id in doctor_ids:
		sync_queue_for_day(doctor_id, for_date)

	queue_items = {
		item.appointment_id: item
		for item in QueueItem.objects.select_related("appointment").filter(slot_date=for_date)
	}
	latest_called = (
		QueueItem.objects
		.filter(slot_date=for_date, status="CALLED")
		.order_by("-called_at")
		.first()
	)

	appointments = (
		Appointment.objects
		.select_related("patient", "doctor")
		.filter(slot_date=for_date)
		.exclude(status="CANCELLED")
		.order_by("doctor__full_name", "start_time")
	)

	return JsonResponse({
		"date": str(for_date),
		"latest_called_appointment_id": latest_called.appointment_id if latest_called else None,
		"appointments": [
			{
				"appointment_id": a.id,
				"doctor_id": a.doctor_id,
				"doctor_name": a.doctor.display_name,
				"patient_id": a.patient_id,
				"patient_name": f"{a.patient.first_name} {a.patient.last_name}",
				"mobile": a.patient.phone,
				"opd_number": a.opd_number,
				"start_time": a.start_time.strftime("%H:%M"),
				"status": a.status,
				"queue_token": queue_items[a.id].token_number if a.id in queue_items else None,
				"queue_status": queue_items[a.id].status if a.id in queue_items else "NOT_IN_QUEUE",
			}
			for a in appointments
		],
	})
```

**Key Features**:
- Shows all doctors' appointments for today
- Grouped and ordered by doctor name, then start_time
- Syncs queue automatically
- Tracks latest called appointment across all doctors

---

## 7. QUEUE MANAGEMENT VIEW FUNCTIONS

### 7.1 Queue Board Display
**Location**: `backend/apps/core/views.py` (Lines 1499-1509)  
**Route**: `GET /api/queue/board/`

```python
@require_GET
@login_required
@role_required("Receptionist", "Doctor", "Admin")
def queue_board(request):
	form = QueueBoardForm(request.GET)
	if not form.is_valid():
		return JsonResponse({"error": "validation_failed", "details": form.errors}, status=400)

	items = list_queue_board(
		doctor_id=form.cleaned_data["doctor_id"],
		slot_date=form.cleaned_data["slot_date"],
	)
	return JsonResponse({"items": items})
```

### 7.2 Call Next Patient (NEXT PATIENT BUTTON)
**Location**: `backend/apps/core/views.py` (Lines 1514-1536)  
**Route**: `POST /api/queue/call-next/`  
**Decorators**: `@require_POST`, `@login_required`, `@role_required("Receptionist", "Doctor", "Admin")`

```python
@require_POST
@login_required
@role_required("Receptionist", "Doctor", "Admin")
def queue_call_next(request):
	form = QueueCallNextForm(request.POST)
	if not form.is_valid():
		return JsonResponse({"error": "validation_failed", "details": form.errors}, status=400)

	try:
		queue_item, _, payload = call_next(
			doctor_id=form.cleaned_data["doctor_id"],
			slot_date=form.cleaned_data["slot_date"],
			actor_username=request.user.username,
		)
	except ValueError as exc:
		if str(exc) == "queue_empty":
			return JsonResponse({"error": "queue_empty"}, status=409)
		raise

	return JsonResponse({
		"status": queue_item.status,
		"queue_item_id": queue_item.id,
		"event": payload,
	})
```

---

## 8. BUSINESS LOGIC - SERVICE LAYER FUNCTIONS

**Location**: `backend/apps/core/services.py`

### 8.1 Complete Appointment
**Lines**: 391-416

```python
@transaction.atomic
def complete_appointment(appointment, actor_username):
    target_status = "COMPLETED"
    if not is_transition_allowed(appointment.status, target_status):
        raise ValueError("invalid_transition")

    previous = appointment.status
    appointment.status = target_status
    appointment.save(update_fields=["status", "updated_at"])

    AppointmentEvent.objects.create(
        appointment=appointment,
        action="COMPLETE",
        previous_status=previous,
        new_status=target_status,
        reason="doctor_completed_visit",
        actor_username=actor_username,
    )

    queue_item = QueueItem.objects.select_for_update().filter(appointment=appointment).first()
    if queue_item and queue_item.status != "COMPLETED":
        previous_queue_status = queue_item.status
        queue_item.status = "COMPLETED"
        queue_item.save(update_fields=["status", "updated_at"])
        _create_queue_event(queue_item, "COMPLETE", previous_queue_status, "COMPLETED", actor_username)

    return appointment
```

**Key Behavior**:
- Validates transition is allowed (BOOKED/RESCHEDULED → COMPLETED only)
- Updates appointment status to COMPLETED
- Creates AppointmentEvent audit record
- Also updates linked QueueItem status to COMPLETED if present
- Creates QueueEvent audit record

---

### 8.2 Sync Queue For Day
**Lines**: 478-506

```python
def sync_queue_for_day(doctor_id, slot_date):
    active_appointments = Appointment.objects.filter(
        doctor_id=doctor_id,
        slot_date=slot_date,
        status__in=["BOOKED", "RESCHEDULED"],
    ).order_by("created_at")

    created_count = 0
    for appointment in active_appointments:
        if hasattr(appointment, "queue_item"):
            continue
        QueueItem.objects.create(
            appointment=appointment,
            doctor_id=doctor_id,
            slot_date=slot_date,
            token_number=_next_token_number(doctor_id, slot_date),
            status="WAITING",
        )
        created_count += 1
    return created_count
```

**Key Behavior**:
- Auto-creates QueueItems for appointments in BOOKED or RESCHEDULED status
- Creates QueueItem with status WAITING
- Assigns token_number in order of appointment creation (created_at)
- Idempotent: doesn't recreate if QueueItem already exists
- Returns count of new QueueItems created

---

### 8.3 Call Next Patient Implementation
**Lines**: 550-568

```python
@transaction.atomic
def call_next(doctor_id, slot_date, actor_username):
    sync_queue_for_day(doctor_id, slot_date)
    queue_item = (
        QueueItem.objects.select_for_update()
        .filter(doctor_id=doctor_id, slot_date=slot_date, status="WAITING")
        .order_by("token_number")
        .first()
    )
    if not queue_item:
        raise ValueError("queue_empty")

    previous = queue_item.status
    queue_item.status = "CALLED"
    queue_item.called_at = timezone.now()
    queue_item.save(update_fields=["status", "called_at", "updated_at"])
    event, payload = _create_queue_event(queue_item, "CALL_NEXT", previous, "CALLED", actor_username)
    return queue_item, event, payload
```

**Next Patient Button Logic**:
1. Syncs queue for the day (creates any missing QueueItems)
2. Finds first WAITING item by token_number (FIFO order)
3. If no WAITING items, raises ValueError("queue_empty")
4. Transitions found item to CALLED status
5. Records called_at timestamp
6. Creates QueueEvent audit record
7. Returns queue_item, event, and payload

---

### 8.4 List Queue Board
**Lines**: 526-545

```python
def list_queue_board(doctor_id, slot_date):
    sync_queue_for_day(doctor_id, slot_date)
    items = QueueItem.objects.filter(doctor_id=doctor_id, slot_date=slot_date).order_by("token_number")
    board = []
    waiting_position = 0
    for item in items:
        if item.status in {"WAITING", "CALLED", "SKIPPED"}:
            waiting_position += 1
            estimated_wait_minutes = max(waiting_position - 1, 0) * 10
        else:
            estimated_wait_minutes = 0
        board.append(
            {
                "queue_item_id": item.id,
                "appointment_id": item.appointment_id,
                "token_number": item.token_number,
                "status": item.status,
                "estimated_wait_minutes": estimated_wait_minutes,
            }
        )
    return board
```

**Queue Display Logic**:
- Syncs queue for day (auto-creates QueueItems)
- Returns items ordered by token_number
- Calculates estimated wait time: (position - 1) * 10 minutes
- Wait time only calculated for WAITING, CALLED, or SKIPPED items
- COMPLETED/NO_SHOW items have 0 estimated wait

---

### 8.5 Queue Action (Skip, Recall, No Show)
**Lines**: 570-592

```python
@transaction.atomic
def queue_action(queue_item_id, action, actor_username):
    queue_item = QueueItem.objects.select_for_update().get(id=queue_item_id)
    action_map = {
        "SKIP": "SKIPPED",
        "RECALL": "CALLED",
        "NO_SHOW": "NO_SHOW",
    }
    if action not in action_map:
        raise ValueError("invalid_action")

    target_status = action_map[action]
    if not _queue_transition_allowed(queue_item.status, target_status):
        raise ValueError("invalid_transition")

    previous = queue_item.status
    queue_item.status = target_status
    if target_status == "CALLED":
        queue_item.called_at = timezone.now()
        queue_item.save(update_fields=["status", "called_at", "updated_at"])
    else:
        queue_item.save(update_fields=["status", "updated_at"])

    event, payload = _create_queue_event(queue_item, action, previous, target_status, actor_username)
    return queue_item, event, payload
```

**Actions Supported**:
- **SKIP**: WAITING/CALLED/SKIPPED → SKIPPED (can skip multiple times for callbacks)
- **RECALL**: SKIPPED → CALLED (bring patient back)
- **NO_SHOW**: WAITING/CALLED/SKIPPED → NO_SHOW (patient didn't show)

---

## 9. FRONT-END TEMPLATES

### 9.1 Doctor Queue Page
**Location**: `frontend/templates/doctor_queue.html`

```html
<h2>View Queue Board</h2>
<form id="queueBoardForm" class="form-inline">
    <label>Doctor ID <input type="number" name="doctor_id" min="1" required /></label>
    <label>Slot Date <input type="date" name="slot_date" required /></label>
    <button type="submit">View Queue</button>
</form>

<h2>Call Next Patient</h2>
<form id="queueCallNextForm" class="form-inline">
    <label>Doctor ID <input type="number" name="doctor_id" min="1" required /></label>
    <label>Slot Date <input type="date" name="slot_date" required /></label>
    <button type="submit">Call Next</button>
</form>
```

---

### 9.2 Doctor Appointments Page
**Location**: `frontend/templates/doctor_appointments.html` (Lines 1-200+)

```html
<h2>View Appointments</h2>
<button onclick="loadAppointmentsForDate('tomorrow')">Load Tomorrow's Appointments</button>
<div id="appointmentsList"></div>

<h2>Appointment Calendar & Statistics</h2>
<!-- Calendar with daywise appointment counts and revenue -->
```

**Key Features**:
- Displays doctor's appointments for today/tomorrow
- Shows patient name, mobile, appointment time
- Shows queue token and queue status
- Calendar view with appointment counts per day
- Monthly statistics and revenue tracking

---

### 9.3 Doctor Consultation Page
**Location**: `frontend/templates/doctor_consultation.html` (Key Section)

```html
<button type="button" id="nextPatientBtn" disabled
    style="...background:#27ae60; color:#fff; ...">NEXT patient</button>
```

**Key Features**:
- **NEXT patient button**: Calls next patient from queue
- Consultation draft form with:
  - Chief complaint (C/O)
  - Diagnosis
  - Vitals section (Temp, Pulse, BP, SpO2, Weight)
  - Known history updater
  - Medicine prescription table (Indian format)
  - Follow-up date
  - Lab orders
- Previous history display
- Last prescription display
- Billing add-ons section
- Prescription issuance and editing

---

## 10. CURRENT APPOINTMENT QUEUE ORDERING & DISPLAY

### Ordering
**Primary**: Token Number (FIFO)  
**Secondary**: Slot Date → Start Time

### Queue Item Creation
- **Trigger**: `sync_queue_for_day()` function
- **Timing**: Automatically called before viewing appointments or calling next
- **Scope**: Creates QueueItems for all BOOKED and RESCHEDULED appointments for a doctor on a given date
- **Order**: Token numbers assigned in order of appointment `created_at` (creation order, not slot order)

### Queue Status Tracking
- **Initial**: WAITING (when QueueItem created)
- **Progression**: WAITING → CALLED (when doctor clicks "Next Patient")
- **Outcomes**: COMPLETED, SKIPPED, NO_SHOW

### Display Elements in Queue Board
- Token Number
- Queue Status (WAITING, CALLED, SKIPPED, COMPLETED, NO_SHOW)
- Estimated Wait Time (calculated as: (position - 1) × 10 minutes)

---

## 11. CONSULTATION STATUS TRANSITIONS

**Location**: `backend/apps/core/services.py` (Lines 623-655)

```python
CONSULTATION_EDITABLE_FIELDS = {"chief_complaint", "findings", "diagnosis", "notes", "follow_up_date"}

@transaction.atomic
def create_or_update_consultation_draft(appointment_id, data, actor_username):
    appointment = Appointment.objects.get(id=appointment_id)
    consultation, _ = Consultation.objects.get_or_create(
        appointment=appointment,
        defaults={
            "doctor_id": appointment.doctor_id,
            "patient_id": appointment.patient_id,
            "created_by": actor_username,
        },
    )
    if consultation.status == "FINALIZED":
        raise ValueError("already_finalized")

    for field in CONSULTATION_EDITABLE_FIELDS:
        if field in data:
            setattr(consultation, field, data[field])
    consultation.save()
    return consultation

@transaction.atomic
def finalize_consultation(consultation_id, actor_username):
    consultation = Consultation.objects.select_for_update().get(id=consultation_id)
    if consultation.status == "FINALIZED":
        raise ValueError("already_finalized")

    consultation.status = "FINALIZED"
    consultation.finalized_by = actor_username
    consultation.finalized_at = timezone.now()
    consultation.save(update_fields=["status", "finalized_by", "finalized_at", "updated_at"])
    return consultation
```

### Consultation Workflow
1. **Create/Update Draft**: Consultation auto-created in DRAFT status when first accessed
2. **Draft Editing**: Editable fields: chief_complaint, findings, diagnosis, notes, follow_up_date
3. **Finalize**: Doctor clicks "Save Consultation" → transitions to FINALIZED
4. **Lock**: Once FINALIZED, no further edits allowed (attempted changes raise ValueError)

---

## 12. EXISTING PAUSE/RESUME FUNCTIONALITY

### Current Status: **NOT IMPLEMENTED**

**Search Results**:
- No matches for "pause", "resume", "PAUSED", or "RESUMED" in codebase
- No pause/resume status options in Appointment or QueueItem models
- No business logic functions handling pause/resume transitions

### Current Pause Equivalent
- **Closest mechanism**: SKIPPED status in queue
  - QueueItem can be moved to SKIPPED (via `queue_action` with action="SKIP")
  - Can be recalled from SKIPPED back to CALLED (via `queue_action` with action="RECALL")
  - But this is patient-level skip, not appointment-level pause

---

## 13. APPOINTMENT EVENT AUDIT TRAIL

**Location**: `backend/apps/core/models.py` (Lines 161-175)

```python
class AppointmentEvent(models.Model):
	ACTION_CHOICES = [
		("BOOK", "Book"),
		("RESCHEDULE", "Reschedule"),
		("COMPLETE", "Complete"),
		("CANCEL", "Cancel"),
	]

	appointment = models.ForeignKey(Appointment, on_delete=models.CASCADE, related_name="events")
	action = models.CharField(max_length=20, choices=ACTION_CHOICES)
	previous_status = models.CharField(max_length=20, blank=True, default="")
	new_status = models.CharField(max_length=20)
	reason = models.CharField(max_length=255, blank=True, default="")
	actor_username = models.CharField(max_length=150)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["created_at"]
```

---

## 14. QUEUE EVENT AUDIT TRAIL

**Location**: `backend/apps/core/models.py` (Lines 334-360)

```python
class QueueEvent(models.Model):
	ACTION_CHOICES = [
		("CALL_NEXT", "Call Next"),
		("SKIP", "Skip"),
		("RECALL", "Recall"),
		("COMPLETE", "Complete"),
		("NO_SHOW", "No Show"),
	]

	queue_item = models.ForeignKey(QueueItem, on_delete=models.CASCADE, related_name="events")
	action = models.CharField(max_length=20, choices=ACTION_CHOICES)
	previous_status = models.CharField(max_length=20)
	new_status = models.CharField(max_length=20)
	actor_username = models.CharField(max_length=150)
	payload = models.JSONField(default=dict)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["created_at"]
```

---

## 15. SUMMARY TABLE

| Aspect | Status | Details |
|--------|--------|---------|
| **Appointment Status Options** | ✅ Implemented | BOOKED, RESCHEDULED, COMPLETED, CANCELLED |
| **Consultation Status Options** | ✅ Implemented | DRAFT, FINALIZED |
| **Queue Status Options** | ✅ Implemented | WAITING, CALLED, SKIPPED, COMPLETED, NO_SHOW |
| **State Transitions** | ✅ Implemented | Enforced via transition matrix in services |
| **Next Patient Logic** | ✅ Implemented | `call_next()` function in services.py |
| **Appointment Listing** | ✅ Implemented | `doctor_today_appointments()` view |
| **Queue Display** | ✅ Implemented | `list_queue_board()` service |
| **Audit Trail** | ✅ Implemented | AppointmentEvent, QueueEvent models |
| **Pause/Resume** | ❌ Not Implemented | No pause status; closest is SKIPPED queue status |
| **Appointment Ordering** | ✅ By Creation | Token number assigned by appointment creation order |
| **Frontend NEXT Button** | ✅ Implemented | `doctor_consultation.html` template |

---

## 16. DATA FLOW - "NEXT PATIENT" BUTTON

```
User clicks "NEXT patient" button
    ↓
POST /api/queue/call-next/ (queue_call_next view)
    ↓
Calls services.call_next(doctor_id, slot_date, actor_username)
    ↓
Step 1: sync_queue_for_day(doctor_id, slot_date)
    → Creates QueueItems for all BOOKED/RESCHEDULED appointments
    
Step 2: Find first WAITING QueueItem by token_number
    → Uses select_for_update() for transaction safety
    
Step 3: Transition WAITING → CALLED
    → Updates queue_item.status = "CALLED"
    → Records called_at timestamp
    
Step 4: Create QueueEvent audit record
    → Logs action, previous/new status, actor username
    
Step 5: Return queue_item, event, payload
    ↓
Frontend receives response with queue_item_id and new status
    ↓
Frontend updates UI to highlight called patient
```

---

## 17. KEY ENDPOINTS SUMMARY

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/appointments/today/` | GET | Get doctor's appointments for today/tomorrow |
| `/api/appointments/board/today/` | GET | Get all doctors' appointments for today (receptionist view) |
| `/api/queue/board/` | GET | Display queue board for specific doctor/date |
| `/api/queue/call-next/` | POST | Call next waiting patient |
| `/api/queue/mark-called/{appointment_id}/` | POST | Mark specific appointment as called |
| `/api/queue/skip/{queue_item_id}/` | POST | Skip patient in queue |
| `/api/queue/recall/{queue_item_id}/` | POST | Recall skipped patient |
| `/api/queue/no-show/{queue_item_id}/` | POST | Mark patient as no-show |

---

**End of Codebase Exploration Summary**
