# Emergency Interrupt Workflow Specification
**Date:** May 9, 2026  
**Status:** Requirements Definition  
**Author:** Mary (Business Analyst)

---

## Table of Contents
1. [Problem Statement](#problem-statement)
2. [Scope & Constraints](#scope--constraints)
3. [User Personas & Workflows](#user-personas--workflows)
4. [System Architecture](#system-architecture)
5. [Data Model Changes](#data-model-changes)
6. [API Specifications](#api-specifications)
7. [Frontend UI/UX Specifications](#frontend-uiux-specifications)
8. [State Machines](#state-machines)
9. [Edge Cases & Error Handling](#edge-cases--error-handling)
10. [Testing Strategy](#testing-strategy)
11. [Implementation Sequence](#implementation-sequence)

---

## 1. Problem Statement

**Current Situation:**
A doctor is consulting with Patient A (QueueItem.CALLED). Suddenly an emergency patient arrives and the doctor must attend to them immediately. The current system has no mechanism to:
- Pause Patient A's consultation without marking it COMPLETED
- Jump the emergency patient to the front of the queue
- Resume Patient A's consultation after the emergency
- Show accurate status in the appointment queue

**Desired Outcome:**
A seamless workflow where doctors can pause consultations, handle emergencies, and resume paused consultations without confusing receptionists or patients.

---

## 2. Scope & Constraints

### In Scope
✅ Pause/Resume consultation logic  
✅ Emergency patient queue priority  
✅ Status display accuracy in appointment queue  
✅ "Next Patient" button behavior during pause/resume  
✅ Audit trail for all state transitions  
✅ Doctor-facing pause button  
✅ Receptionist-facing emergency add flow  

### Out of Scope (Future)
❌ Multiple simultaneous paused consultations per doctor  
❌ Patient notification system (SMS/email on delay)  
❌ Advanced queue analytics  
❌ Predictive wait time estimation  
❌ SLA breach warnings  

### Constraints
- **Single Active Consultation:** Only one consultation can be CALLED (in progress) per doctor at a time
- **FIFO + Priority:** Normal queue is FIFO (token_number), emergencies jump to front
- **Non-Destructive:** Pausing must preserve consultation state (no data loss)
- **Backward Compatible:** Existing COMPLETED/CANCELLED flows must work unchanged

---

## 3. User Personas & Workflows

### 3.1 Doctor Persona — Dr. Rajesh
**Goal:** Consult efficiently without queue management overhead  
**Pain Points:** 
- Cannot pause when emergency arrives
- Unsure if "Next" button will call right patient after emergency
- Cannot see who's paused vs waiting

**Workflow:**
```
1. Doctor clicks "NEXT" → Patient A called (QueueItem.CALLED)
2. Doctor begins consultation with Patient A
3. [EMERGENCY ARRIVES]
4. Doctor clicks "PAUSE CURRENT CONSULTATION"
   → Patient A's QueueItem → PAUSED (consultation saved)
5. Reception calls next patient (Patient B) OR emergency patient
6. Doctor handles Patient B / Emergency
7. When ready to resume:
   Doctor clicks "NEXT" → System checks for PAUSED items first
   → Patient A resumed (QueueItem → RESUMED, displayed as "Resuming consultation")
8. Doctor continues with Patient A
9. Doctor completes → QueueItem.COMPLETED
```

### 3.2 Receptionist Persona — Priya
**Goal:** Manage queue smoothly, reduce patient confusion  
**Pain Points:**
- Cannot add emergency patient to front of queue
- Patients waiting for pause resumption don't have status label
- Doesn't know if doctor is paused or just slow

**Workflow:**
```
1. Emergency patient arrives
2. Priya opens appointment queue
3. Priya clicks "Add Emergency Patient" button
4. Priya selects OR creates emergency appointment
5. Appointment is marked is_emergency=True
6. Queue re-renders with emergency patient at position 0
7. Priya can see labels:
   - "⏸ Paused (Dr. Rajesh will resume)" for paused patients
   - "🚨 Emergency" for priority patients
   - "Waiting..." for normal queue
```

### 3.3 Patient Persona — Mrs. Sharma (Normal), Mr. Kumar (Emergency)
**Goal (Normal):** Get consultation at scheduled time  
**Goal (Emergency):** Seen immediately  
**Pain Points (Normal):** 
- Doesn't understand why consultation was paused
- Confused about wait time

---

## 4. System Architecture

### 4.1 Component Interactions
```
┌─────────────────────────────────────────────────────────┐
│                    Doctor Workbench                      │
│  [NEXT Patient] [PAUSE Consultation] [Complete/Notes]    │
└──────────────┬──────────────────────────────────────────┘
               │ API Calls
               ↓
┌──────────────────────────────────────────────────────────┐
│              Backend Services (views.py)                  │
│  • call_next() [LOGIC CHANGE]                            │
│  • pause_current_consultation() [NEW]                    │
│  • resume_consultation() [IMPLICIT in call_next]         │
│  • add_emergency_patient() [NEW]                         │
│  • get_queue_status() [LOGIC CHANGE]                     │
└──────────────┬──────────────────────────────────────────┘
               │ ORM
               ↓
┌──────────────────────────────────────────────────────────┐
│              Database (models.py)                         │
│  • QueueItem.status [ADD: PAUSED, RESUMED]               │
│  • Appointment.is_emergency [NEW FIELD]                  │
│  • AuditLog [NEW ENTRIES]                                │
└──────────────────────────────────────────────────────────┘
```

### 4.2 Data Flow on Emergency Interrupt
```
Doctor sees emergency → Clicks "PAUSE"
    ↓
call pause_current_consultation(doctor_id)
    ├─ Find QueueItem.CALLED for this doctor
    ├─ Transition: CALLED → PAUSED
    ├─ Save: paused_at = now()
    ├─ Audit: "Consultation paused by Dr. Rajesh"
    ├─ Update Consultation: status stays DRAFT (not finalized)
    └─ Return: {"status": "paused"}

Receptionist adds emergency patient
    ↓
add_emergency_patient(patient_id, doctor_id)
    ├─ Get or create Appointment
    ├─ Set: is_emergency=True, appointment.status=BOOKED
    ├─ Create QueueItem with is_emergency=True
    ├─ Sync queue ordering (emergency first)
    └─ Return: {"queue_position": 1}

Doctor clicks "NEXT"
    ↓
call_next(doctor_id)
    ├─ Check for PAUSED items (is this doctor's paused patient?)
    │  ├─ If YES: PAUSED → RESUMED (resume first)
    │  └─ If NO: Continue to next step
    ├─ Get first WAITING item (by [is_emergency DESC, token_number ASC])
    ├─ Transition: WAITING → CALLED
    ├─ Audit: "Patient called"
    └─ Return: {"patient": {...}, "status": "called"}
```

---

## 5. Data Model Changes

### 5.1 QueueItem Model Changes
**Location:** `backend/apps/core/models.py` → `class QueueItem`

**Current Status Choices:**
```python
WAITING = "waiting"
CALLED = "called"
SKIPPED = "skipped"
COMPLETED = "completed"
NO_SHOW = "no_show"
```

**New Status Choices (Add):**
```python
PAUSED = "paused"        # Consultation interrupted by doctor
RESUMED = "resumed"      # Paused consultation brought back
```

**New Fields to Add:**
```python
paused_at = DateTimeField(null=True, blank=True)
paused_by = ForeignKey(Doctor, null=True, blank=True, related_name=...)
resume_order_position = PositiveIntegerField(default=0)
```

**Rationale:**
- `paused_at`: Timestamp for audit trail
- `paused_by`: Which doctor paused (for multi-doctor clinics)
- `resume_order_position`: If multiple paused, which resumes first (FIFO among paused)

### 5.2 Appointment Model Changes
**Location:** `backend/apps/core/models.py` → `class Appointment`

**New Field to Add:**
```python
is_emergency = BooleanField(default=False)
marked_emergency_at = DateTimeField(null=True, blank=True)
marked_emergency_by = ForeignKey(User, null=True, blank=True, related_name=...)
```

**Rationale:**
- `is_emergency`: Flag for queue priority sorting
- `marked_emergency_at`: When was it marked (audit)
- `marked_emergency_by`: Who marked it (audit)

### 5.3 Migration Plan
**File:** `backend/apps/core/migrations/0032_emergency_interrupt_support.py`

```
Operations:
1. Add PAUSED, RESUMED to QueueItem.status choices
2. Add paused_at, paused_by, resume_order_position to QueueItem
3. Add is_emergency, marked_emergency_at, marked_emergency_by to Appointment
4. Create database index on (QueueItem.doctor_id, status) for fast resume lookup
5. Create database index on (Appointment.doctor_id, is_emergency) for queue sorting
```

---

## 6. API Specifications

### 6.1 Pause Current Consultation
**Endpoint:** `POST /api/appointments/pause-current/`  
**Requires:** @login_required, @role_required("Doctor")

**Request:**
```json
{
  "reason": "Emergency patient arrival"  // optional
}
```

**Response (Success - 200):**
```json
{
  "status": "success",
  "queue_item_id": 42,
  "patient_name": "Mrs. Sharma",
  "opd_number": "OPD-00000123",
  "paused_at": "2026-05-09T14:35:22Z"
}
```

**Response (Error - 400):**
```json
{
  "status": "error",
  "message": "No consultation currently in progress"
}
```

**Business Logic:**
1. Verify doctor has exactly one QueueItem.CALLED status
2. If not found → return 400 error
3. Transition QueueItem.status: CALLED → PAUSED
4. Save `paused_at`, `paused_by`
5. Create AuditLog entry
6. **Do NOT** modify Consultation (stays DRAFT)
7. Return queue_item details

**Edge Cases:**
- What if doctor is in middle of typing notes? → Consultation auto-saved (existing behavior), pause only affects queue
- What if there are multiple CALLED items (data corruption)? → Return error, alert admin

---

### 6.2 Add Emergency Patient
**Endpoint:** `POST /api/appointments/add-emergency/`  
**Requires:** @login_required, @role_required("Receptionist", "Admin")

**Request (Existing Patient):**
```json
{
  "patient_id": 5,
  "doctor_id": 3,
  "visit_type": "NEW"
}
```

**Request (Walk-in Patient):**
```json
{
  "patient": {
    "first_name": "John",
    "last_name": "Doe",
    "phone": "9876543210"
  },
  "doctor_id": 3,
  "visit_type": "NEW"
}
```

**Response (Success - 201):**
```json
{
  "status": "success",
  "appointment_id": 99,
  "queue_item_id": 50,
  "patient_name": "John Doe",
  "opd_number": "OPD-00000199",
  "queue_position": 1,
  "marked_as_emergency_at": "2026-05-09T14:35:22Z"
}
```

**Business Logic:**
1. If patient_id provided: load existing patient
2. If patient object provided: create or get by phone
3. Create Appointment with:
   - `status=BOOKED`
   - `doctor_id=provided`
   - `is_emergency=True`
   - `slot_date=today()`
   - `start_time=now()`
4. Call `sync_queue_for_day()` (regenerates tokens)
5. Create QueueItem with `token_number` based on new ordering
6. Create AuditLog: "Emergency appointment added"
7. Return appointment + queue position

**Edge Cases:**
- What if patient already has BOOKED appointment today? → Reuse it, set is_emergency=True
- What if doctor has no slots? → Still allow (overflow appointment)
- What if receptionist marks non-emergency as emergency? → Audit logs it, allow

---

### 6.3 Call Next (Modified)
**Endpoint:** `POST /api/appointments/call-next/`  
**Requires:** @login_required, @role_required("Doctor")

**Request:**
```json
{
  "doctor_id": 3  // optional, defaults to request.user.doctor
}
```

**Response (Success - 200):**
```json
{
  "status": "success",
  "queue_item_id": 42,
  "patient_id": 5,
  "patient_name": "Mrs. Sharma",
  "opd_number": "OPD-00000123",
  "visit_type": "FOLLOW_UP",
  "phone": "9876543210",
  "queue_action": "resumed",  // or "called" or "paused"
  "message": "Resuming consultation with Mrs. Sharma"
}
```

**NEW Logic:**
```
1. Sync queue for today
2. Check for PAUSED items with this doctor:
   - If found: Transition PAUSED → RESUMED (status shows "Resuming")
   - Return early with queue_action="resumed"
3. If no PAUSED items:
   - Get first WAITING item (ordered by: is_emergency DESC, token_number ASC)
   - If found: Transition WAITING → CALLED
   - Return with queue_action="called"
4. If no items at all:
   - Return 200 with {"status": "success", "message": "No more patients in queue"}
```

**Key Change:** PAUSED items get priority over WAITING items

---

### 6.4 Get Queue Status (Modified)
**Endpoint:** `GET /api/appointments/queue-status/?doctor_id=3`  
**Requires:** @login_required

**Response:**
```json
{
  "status": "success",
  "doctor_id": 3,
  "queue_summary": {
    "waiting": 5,
    "called": 1,
    "paused": 1,
    "completed": 8,
    "no_show": 1
  },
  "queue_items": [
    {
      "queue_item_id": 50,
      "position": 0,
      "patient_name": "Mr. Kumar",
      "opd_number": "OPD-00000199",
      "status": "called",
      "label": "🚨 Currently Consulting (Emergency)",
      "is_emergency": true
    },
    {
      "queue_item_id": 42,
      "position": 1,
      "patient_name": "Mrs. Sharma",
      "opd_number": "OPD-00000123",
      "status": "paused",
      "label": "⏸ Paused (will resume)",
      "is_emergency": false
    },
    {
      "queue_item_id": 43,
      "position": 2,
      "patient_name": "Patient C",
      "opd_number": "OPD-00000124",
      "status": "waiting",
      "label": "Waiting...",
      "is_emergency": false
    }
  ]
}
```

**Ordering Rules:**
1. CALLED (max 1 per doctor) — position 0
2. PAUSED (in resume order) — positions 1+
3. WAITING (by is_emergency DESC, token_number ASC) — positions N+
4. COMPLETED, NO_SHOW, SKIPPED — not included in live view

---

## 7. Frontend UI/UX Specifications

### 7.1 Doctor Workbench (doctor_appointments.html / doctor_consultation.html)

**Add New Button Section:**
```html
<div class="consultation-controls">
  <!-- Existing -->
  <button id="nextPatientBtn" class="btn-primary">
    📋 Next Patient
  </button>
  
  <!-- NEW -->
  <button id="pauseConsultationBtn" class="btn-warning" style="display: none;">
    ⏸ Pause Consultation
  </button>
  
  <button id="completeConsultationBtn" class="btn-success">
    ✓ Complete & Bill
  </button>
</div>
```

**Button Visibility Logic:**
- `nextPatientBtn`: Always visible
- `pauseConsultationBtn`: **Visible only when consultation in progress** (QueueItem.CALLED)
- `completeConsultationBtn`: Always visible

**Pause Button Behavior:**
```javascript
document.getElementById('pauseConsultationBtn').addEventListener('click', async function() {
  const response = await fetch('/api/appointments/pause-current/', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({reason: 'Emergency'})
  });
  
  if (response.ok) {
    const data = await response.json();
    showNotification('✓ Consultation paused. You can handle the emergency now.');
    // Update UI: show resume UI, hide pause button
    updateQueueDisplay();
  } else {
    showError('Cannot pause: No consultation in progress');
  }
});
```

**Queue Item Display Changes:**
```html
<!-- In appointment queue list -->
<div class="queue-item" data-status="{{item.status}}">
  <div class="queue-badge">
    {% if item.status == 'called' %}
      <span class="badge-called">📞 Calling...</span>
    {% elif item.status == 'paused' %}
      <span class="badge-paused">⏸ Paused</span>
    {% elif item.status == 'waiting' %}
      <span class="badge-waiting">⏳ Waiting</span>
      {% if item.is_emergency %}
        <span class="badge-emergency">🚨 EMERGENCY</span>
      {% endif %}
    {% endif %}
  </div>
  
  <div class="queue-info">
    <strong>{{ item.patient_name }}</strong>
    <div>{{ item.opd_number }}</div>
  </div>
</div>
```

**CSS for New Badges:**
```css
.badge-paused {
  background: #FFA500;
  color: white;
  padding: 4px 8px;
  border-radius: 4px;
  font-weight: bold;
}

.badge-emergency {
  background: #FF4444;
  color: white;
  animation: pulse-emergency 1s infinite;
}

@keyframes pulse-emergency {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.7; }
}
```

---

### 7.2 Receptionist Dashboard (receptionist_appointments.html / workbench_receptionist.html)

**Add Emergency Add Button:**
```html
<div class="receptionist-controls">
  <button id="addEmergencyBtn" class="btn-danger">
    🚨 Add Emergency Patient
  </button>
</div>

<!-- Modal for emergency add -->
<div id="emergencyModal" style="display: none;">
  <h3>Add Emergency Patient</h3>
  
  <!-- Option 1: Existing Patient -->
  <div class="form-section">
    <label>Existing Patient:</label>
    <select id="existingPatientSelect">
      <option value="">-- Search by name/phone --</option>
      <!-- autocomplete options -->
    </select>
  </div>
  
  <!-- Option 2: Walk-in Patient -->
  <div class="form-section">
    <label>Or Create Walk-in:</label>
    <input type="text" id="emergencyFirstName" placeholder="First Name" />
    <input type="text" id="emergencyLastName" placeholder="Last Name" />
    <input type="tel" id="emergencyPhone" placeholder="Phone" />
  </div>
  
  <!-- Doctor Assignment -->
  <div class="form-section">
    <label>Assign to Doctor:</label>
    <select id="emergencyDoctorSelect">
      <option value="">-- Select Doctor --</option>
      <option value="3">Dr. Rajesh Kumar</option>
      <option value="5">Dr. Priya Sharma</option>
    </select>
  </div>
  
  <button id="confirmEmergencyBtn" class="btn-primary">Add to Queue</button>
  <button id="cancelEmergencyBtn" class="btn-secondary">Cancel</button>
</div>
```

**Modal JavaScript Logic:**
```javascript
document.getElementById('addEmergencyBtn').addEventListener('click', function() {
  document.getElementById('emergencyModal').style.display = 'block';
});

document.getElementById('confirmEmergencyBtn').addEventListener('click', async function() {
  const payload = {};
  
  // Determine patient source
  const existingPatient = document.getElementById('existingPatientSelect').value;
  if (existingPatient) {
    payload.patient_id = existingPatient;
  } else {
    payload.patient = {
      first_name: document.getElementById('emergencyFirstName').value,
      last_name: document.getElementById('emergencyLastName').value,
      phone: document.getElementById('emergencyPhone').value
    };
  }
  
  payload.doctor_id = document.getElementById('emergencyDoctorSelect').value;
  payload.visit_type = 'NEW';
  
  const response = await fetch('/api/appointments/add-emergency/', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload)
  });
  
  if (response.ok) {
    const data = await response.json();
    showNotification(`✓ ${data.patient_name} added as emergency (Position: ${data.queue_position})`);
    document.getElementById('emergencyModal').style.display = 'none';
    updateQueueDisplay();
  } else {
    showError('Failed to add emergency patient');
  }
});
```

---

### 7.3 Patient Waiting Area Display (if applicable)

**Queue Board Updates:**
```html
<div class="queue-board">
  <h2>Queue Status - Dr. Rajesh Kumar</h2>
  
  <div class="queue-item current-consulting">
    <div class="status">🚨 Emergency - Currently Being Treated</div>
    <div class="patient">Mr. Kumar (OPD-00000199)</div>
  </div>
  
  <div class="queue-item paused">
    <div class="status">⏸ Paused - Next in Line (will resume)</div>
    <div class="patient">Mrs. Sharma (OPD-00000123)</div>
    <div class="note">Doctor is handling an emergency. Your consultation will resume shortly.</div>
  </div>
  
  <div class="queue-item waiting">
    <div class="status">⏳ Waiting (Position 3)</div>
    <div class="patient">Mr. Singh (OPD-00000124)</div>
  </div>
</div>
```

---

## 8. State Machines

### 8.1 QueueItem Status Transitions
```
WAITING
  ↓ (call_next, no paused items)
CALLED ←──────────────── PAUSED
  ├─────────────────────→ ⏸ (pause_current_consultation)
  │
  ├─→ COMPLETED (finish consultation)
  │
  ├─→ NO_SHOW (patient didn't show)
  │
  └─→ SKIPPED (skip this patient)

PAUSED
  ├─→ RESUMED ──→ CALLED (resume via call_next)
  │
  ├─→ SKIPPED (doctor decides to skip paused patient)
  │
  └─→ NO_SHOW (patient doesn't return after pause)
```

**Allowed Transitions:**
| From | To | Condition |
|------|-----|-----------|
| WAITING | CALLED | call_next() called, no paused items |
| CALLED | PAUSED | pause_current_consultation() called |
| PAUSED | CALLED/RESUMED | call_next() called |
| PAUSED | SKIPPED | skip_patient() called |
| CALLED | COMPLETED | finish_consultation() called |
| CALLED | SKIPPED | skip_patient() called |
| WAITING | SKIPPED | skip_patient() called |
| * | NO_SHOW | Manual override or timeout |

**Invalid Transitions (Error):**
- COMPLETED → anything
- NO_SHOW → anything
- PAUSED → PAUSED (already paused)

---

### 8.2 Appointment Status Transitions (Unchanged)
```
BOOKED
  ├─→ RESCHEDULED (reschedule appointment)
  ├─→ COMPLETED (after consultation finished)
  └─→ CANCELLED (cancel appointment)
```

**Key Point:** `Appointment.status` is independent of `QueueItem.status`
- Pausing a consultation does NOT change Appointment status
- Only when QueueItem.COMPLETED do we update Appointment.COMPLETED

---

## 9. Edge Cases & Error Handling

### 9.1 Emergency Scenarios

| Scenario | Current Behavior | New Behavior | Handling |
|----------|------------------|--------------|----------|
| Doctor clicks "PAUSE" but no consultation in progress | ❌ Not possible | ❌ Error: "No consultation in progress" | Return 400 Bad Request |
| Two doctors try to pause simultaneously | ❌ Race condition | Handled by DB constraint | Last write wins, audit log captures both |
| Emergency patient added while doctor paused | ✓ Works | ✓ Works + emergency gets priority | Emergency at position 1, paused at position 2 |
| Doctor resumes but paused patient left/cancelled | ❌ Error | Return error, remove from queue | Check Appointment.status before resume |
| Receptionist marks normal appointment as emergency | ❌ Not possible | ✓ Allowed | Audit logs the change, queue reflects it |
| Patient arrives late, appointment already paused | ❌ N/A | ✓ Patient can still consult | Resume when they arrive |
| Database sync fails during pause | ❌ Unknown | Uses transaction | If pause fails, QueueItem.status stays CALLED |

### 9.2 Data Integrity Checks

**On Pause:**
```python
def pause_current_consultation(doctor):
    current = QueueItem.objects.filter(
        queue_date=today(),
        doctor=doctor,
        status='called'
    ).first()
    
    if not current:
        raise ValidationError("No consultation in progress")
    
    # Ensure consultation exists and is DRAFT
    if not current.appointment.consultation:
        raise ValidationError("No consultation record found")
    
    if current.appointment.consultation.status == 'finalized':
        raise ValidationError("Cannot pause finalized consultation")
    
    # Atomic transaction
    with transaction.atomic():
        current.status = 'paused'
        current.paused_at = now()
        current.paused_by = doctor
        current.save(update_fields=['status', 'paused_at', 'paused_by'])
```

**On Resume:**
```python
def call_next(doctor):
    # Check for paused items
    paused = QueueItem.objects.filter(
        queue_date=today(),
        doctor=doctor,
        status='paused'
    ).order_by('resume_order_position').first()
    
    if paused:
        # Verify appointment still valid
        if paused.appointment.status == 'cancelled':
            paused.status = 'no_show'
            paused.save()
            return call_next(doctor)  # Recursively get next
        
        # Resume
        paused.status = 'resumed'  # Show "Resuming" label
        paused.save()
        return paused
```

### 9.3 Error Messages (User-Facing)

**Doctor:**
- "❌ No consultation in progress. Start with 'Next Patient'."
- "❌ Cannot pause: Consultation already finalized."
- "✓ Consultation paused. Handle the emergency."
- "✓ Resuming consultation with Mrs. Sharma"

**Receptionist:**
- "✓ Emergency patient added to queue (Position 1)"
- "❌ Please select a patient and doctor"
- "❌ Doctor not found"
- "⚠️ Patient already has appointment today. Marked as emergency."

---

## 10. Testing Strategy

### 10.1 Unit Tests (models.py, services.py)

**Test: Pause Current Consultation**
```python
def test_pause_current_consultation_success(self):
    # Create: doctor, patient, appointment, queue item
    # Set: queue_item.status = 'called'
    # Call: pause_current_consultation(doctor)
    # Assert: queue_item.status == 'paused'
    # Assert: queue_item.paused_at is not None
    # Assert: queue_item.paused_by == doctor

def test_pause_no_consultation_in_progress(self):
    # Create: doctor with no CALLED queue items
    # Call: pause_current_consultation(doctor)
    # Assert: ValidationError raised

def test_pause_finalized_consultation_fails(self):
    # Create: queue_item.CALLED with finalized consultation
    # Call: pause_current_consultation(doctor)
    # Assert: ValidationError raised
```

**Test: Call Next with Paused Items**
```python
def test_call_next_resumes_paused_first(self):
    # Create: queue with [paused_patient, waiting_patient_1, waiting_patient_2]
    # Call: call_next(doctor)
    # Assert: returned patient == paused_patient
    # Assert: paused_patient.status == 'resumed'

def test_call_next_normal_if_no_paused(self):
    # Create: queue with [waiting_1, waiting_2] (no paused)
    # Call: call_next(doctor)
    # Assert: returned patient == waiting_1
    # Assert: waiting_1.status == 'called'

def test_call_next_emergency_priority(self):
    # Create: queue with [waiting_normal, emergency_waiting]
    # Call: call_next(doctor)
    # Assert: returned patient == emergency_waiting
```

**Test: Add Emergency Patient**
```python
def test_add_emergency_patient_existing(self):
    # Create: existing patient
    # Call: add_emergency_patient(patient_id, doctor_id)
    # Assert: appointment.is_emergency == True
    # Assert: appointment in queue at position 1

def test_add_emergency_patient_walkin(self):
    # Call: add_emergency_patient({first_name, last_name, phone}, doctor_id)
    # Assert: new patient created
    # Assert: new appointment created with is_emergency=True

def test_emergency_moves_to_front(self):
    # Setup: 5 waiting patients
    # Call: add_emergency_patient(new_patient)
    # Assert: emergency_position == 1
    # Assert: other patients shifted to positions 2-6
```

### 10.2 Integration Tests (views.py)

**Test: Full Pause → Resume Workflow**
```python
def test_pause_and_resume_workflow(self):
    # 1. Doctor calls next → Patient A starts
    # 2. Doctor pauses → Status = PAUSED
    # 3. Receptionist adds emergency → Position = 1
    # 4. Doctor calls next → Gets emergency patient
    # 5. Doctor completes emergency → Back to normal queue
    # 6. Doctor calls next → Resumes Patient A (now RESUMED)
```

### 10.3 UI/Frontend Tests (Selenium/Cypress)

**Test: Pause Button Visibility**
```javascript
it('shows pause button only when consultation in progress', () => {
  cy.visit('/doctor/appointments');
  cy.get('#pauseConsultationBtn').should('not.be.visible');
  
  cy.get('#nextPatientBtn').click();
  cy.get('#pauseConsultationBtn').should('be.visible');
});
```

**Test: Emergency Add Modal**
```javascript
it('adds emergency patient and updates queue', () => {
  cy.get('#addEmergencyBtn').click();
  cy.get('#emergencyFirstName').type('John');
  cy.get('#emergencyLastName').type('Doe');
  cy.get('#emergencyPhone').type('9876543210');
  cy.get('#emergencyDoctorSelect').select('3');
  cy.get('#confirmEmergencyBtn').click();
  
  cy.get('.notification').should('contain', 'added as emergency');
  cy.get('.queue-item:first').should('contain', 'John Doe');
});
```

---

## 11. Implementation Sequence

### Phase 1: Backend Foundation (2-3 hours)
1. **Create Migration:** Add status choices, new fields
2. **Update Models:** QueueItem + Appointment changes
3. **Write Services:** pause_current_consultation(), add_emergency_patient(), modify call_next()
4. **Write Unit Tests:** Ensure all service logic tested
5. **Validate:** Run tests, check migrations

### Phase 2: API Endpoints (1-2 hours)
1. **Create Endpoints:** POST /pause-current/, POST /add-emergency/, modify GET /queue-status/
2. **Add Validations:** Permission checks, data validation
3. **Write Integration Tests:** End-to-end flows
4. **Documentation:** API docs with examples

### Phase 3: Frontend - Doctor Workbench (1-2 hours)
1. **Update HTML:** Add pause button
2. **Add JavaScript:** Button click handlers, status display updates
3. **Update Queue Display:** Show pause/resume labels
4. **Test:** Doctor workflow end-to-end

### Phase 4: Frontend - Receptionist (1-2 hours)
1. **Add Emergency Modal:** HTML + CSS
2. **Add JavaScript:** Form handling, API calls
3. **Update Queue Display:** Emergency badges
4. **Test:** Receptionist workflow end-to-end

### Phase 5: Integration & Polish (1 hour)
1. **End-to-End Testing:** Full pause → emergency → resume flow
2. **Audit Logging:** Verify all events logged
3. **Error Handling:** Test edge cases
4. **Documentation:** Update user guides

---

## Appendix A: Database Schema Diff

```sql
-- NEW FIELDS on QueueItem
ALTER TABLE core_queueitem ADD COLUMN paused_at DATETIME NULL;
ALTER TABLE core_queueitem ADD COLUMN paused_by_id INT NULL;
ALTER TABLE core_queueitem ADD COLUMN resume_order_position INT DEFAULT 0;
ALTER TABLE core_queueitem ADD FOREIGN KEY (paused_by_id) REFERENCES core_doctor(id);

-- NEW FIELDS on Appointment
ALTER TABLE core_appointment ADD COLUMN is_emergency BOOLEAN DEFAULT FALSE;
ALTER TABLE core_appointment ADD COLUMN marked_emergency_at DATETIME NULL;
ALTER TABLE core_appointment ADD COLUMN marked_emergency_by_id INT NULL;
ALTER TABLE core_appointment ADD FOREIGN KEY (marked_emergency_by_id) REFERENCES auth_user(id);

-- NEW INDEXES
CREATE INDEX idx_queue_doctor_status ON core_queueitem(doctor_id, status);
CREATE INDEX idx_appointment_emergency ON core_appointment(doctor_id, is_emergency);
```

---

## Sign-Off

**Prepared By:** Mary (Business Analyst)  
**Date:** May 9, 2026  
**Status:** Ready for Developer Review  
**Next Step:** Amelia (Developer) implements Phase 1

---
