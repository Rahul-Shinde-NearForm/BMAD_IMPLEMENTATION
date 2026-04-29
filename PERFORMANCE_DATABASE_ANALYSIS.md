# OPD Management System - Database & Query Performance Analysis

**Generated:** April 29, 2026  
**Supplement to:** PERFORMANCE_ANALYSIS.md, PERFORMANCE_NETWORK_SCENARIOS.md

---

## Database Performance Baseline

### Current Setup

- **Database:** SQLite (development), PostgreSQL (production-ready)
- **Migrations Applied:** 0001 through 0013
- **ORM:** Django ORM with custom services layer
- **Indexing Status:** Basic (migration-level indexes)

---

## Critical Queries Performance Profile

### 1. Patient Search Query

**Service:** `find_duplicate_candidates()` and `search_patients()`  
**File:** [backend/apps/core/services.py](backend/apps/core/services.py#L50-L100)

**Query Pattern:**
```python
# Finds duplicates by phone/DOB matching
Patient.objects.filter(
    Q(phone__iexact=phone) | 
    Q(dob=dob, phone__regex=phone_pattern)
).values('id', 'mrn', 'name', 'phone', 'dob')
```

**Expected Performance:**
| Database | Record Count | Query Time | Status |
|----------|-------------|-----------|--------|
| SQLite (10K records) | 10,000 | 50-100 ms | ⚠️ Acceptable |
| PostgreSQL (100K records) | 100,000 | 20-50 ms | ✅ Good |
| PostgreSQL (1M records) | 1,000,000 | 50-200 ms | ⚠️ Degraded |

**Recommended Indexes:**
```sql
-- PostgreSQL
CREATE INDEX idx_patient_phone ON core_patient(phone);
CREATE INDEX idx_patient_dob ON core_patient(dob);
CREATE INDEX idx_patient_phone_dob ON core_patient(phone, dob);
```

**Optimization Strategies:**
1. Add composite index on (phone, dob)
2. Pre-filter by date range if searching for old records
3. Implement pagination for large result sets
4. Cache recent searches for 5 minutes

**Current Status:** ✅ Acceptable for typical clinic (200-500 patients/month)

---

### 2. Appointment Conflict Detection

**Service:** `book_appointment()`  
**File:** [backend/apps/core/services.py](backend/apps/core/services.py#L140-L160)

**Query Pattern:**
```python
# Check for overlapping appointments
conflicting = Appointment.objects.filter(
    doctor=doctor,
    slot_date=slot_date,
    status__in=['BOOKED', 'RESCHEDULED'],
    start_time__lt=end_time,
    end_time__gt=start_time
)
```

**Expected Performance:**
| Scenario | Doctor's Daily Load | Query Time |
|----------|------------------|-----------|
| Sparse schedule (5 appts/day) | 5 | 5-10 ms |
| Normal schedule (20 appts/day) | 20 | 10-20 ms |
| Busy schedule (40 appts/day) | 40 | 20-50 ms |
| Overbooking (100+ appts/day) | 100+ | 100+ ms |

**Recommended Indexes:**
```sql
CREATE INDEX idx_appointment_doctor_date_status 
  ON core_appointment(doctor_id, slot_date, status);
CREATE INDEX idx_appointment_time_range 
  ON core_appointment(start_time, end_time);
```

**Optimization Strategies:**
1. Add compound index on (doctor_id, slot_date, status)
2. Add partial index for active appointments only
3. Implement read replica for high-volume queries
4. Cache doctor's daily schedule for 1 minute

**Current Status:** ✅ Good. Typical clinic has 40-60 appointments/day.

---

### 3. Queue Board Query

**Service:** `list_queue_board()`  
**File:** [backend/apps/core/services.py](backend/apps/core/services.py#L280-L320)

**Query Pattern:**
```python
# Fetch queue items with patient details
queue_items = QueueItem.objects.filter(
    appointment__slot_date=date,
    appointment__location=location
).select_related('patient', 'appointment__doctor').order_by('created_at')
```

**Expected Performance:**
| Location | Queue Size | Query Time | Result Time |
|----------|-----------|-----------|-------------|
| Single OPD | 30 patients | 20 ms | 40 ms |
| Multi-specialty | 100 patients | 50 ms | 100 ms |
| Large hospital | 500+ patients | 200+ ms | 500+ ms |

**Current Implementation:**
- Uses `select_related()` for patient and doctor (1 query per OPD)
- Ordered by creation time for FIFO queue

**Recommended Indexes:**
```sql
CREATE INDEX idx_queue_date_location 
  ON core_queueitem(appointment_id, slot_date);
CREATE INDEX idx_queue_created_at 
  ON core_queueitem(created_at);
```

**Optimization Strategies:**
1. Cache queue board for 5 seconds (updates via WebSocket)
2. Implement real-time queue updates with Django Channels
3. Separate read/write operations (background worker updates)
4. Store queue state in Redis for instant retrieval

**Current Status:** ✅ Good for single clinic. Needs optimization for multi-location.

---

### 4. Consultation & Vitals Queries

**Service:** `create_or_update_consultation_draft()`, `record_vitals()`  
**File:** [backend/apps/core/services.py](backend/apps/core/services.py#L400-L500)

**Query Patterns:**
```python
# Fetch/create consultation draft
consultation = Consultation.objects.get_or_create(
    appointment=appointment,
    defaults={'doctor': doctor, 'created_by': user}
)

# Record vitals
Vitals.objects.create(
    consultation=consultation,
    temperature_c=temp, pulse_bpm=pulse,
    recorded_by=user
)
```

**Expected Performance:**
| Operation | Query Time | Status |
|-----------|-----------|--------|
| Get/create consultation | 5-10 ms | ✅ Good |
| Record vitals | 5 ms | ✅ Good |
| Amendment history (50 amendments) | 20 ms | ✅ Good |

**Recommended Indexes:**
```sql
CREATE INDEX idx_consultation_appointment 
  ON core_consultation(appointment_id);
CREATE INDEX idx_vitals_consultation 
  ON core_vitals(consultation_id);
CREATE INDEX idx_amendment_consultation 
  ON core_consultationamendment(consultation_id);
```

**Optimization Strategies:**
1. Denormalize vitals count for quick stats
2. Archive old consultations to separate table after 90 days
3. Implement soft-delete for amendments (preserve audit trail)

**Current Status:** ✅ Excellent. Schema is optimal for this workflow.

---

### 5. Prescription Query

**Service:** `issue_prescription()`  
**File:** [backend/apps/core/services.py](backend/apps/core/services.py#L600-L650)

**Query Pattern:**
```python
# Store prescription items as JSON (no separate table)
prescription = Prescription.objects.create(
    consultation=consultation,
    items=items_json,  # Array of {drug, dosage_form, strength, ...}
    rx_number=generate_rx_number(),
    issued_by=user
)
```

**Expected Performance:**
| Operation | JSON Size | Query Time |
|-----------|-----------|-----------|
| Simple prescription (3 items) | ~200 bytes | 5 ms |
| Complex prescription (10 items) | ~800 bytes | 5 ms |
| Fetch 100 prescriptions | ~80 KB | 30 ms |

**Current Design:**
- JSON storage avoids N+1 problem (prescription items)
- Single INSERT operation
- Minimal overhead

**Status:** ✅ Excellent. JSON storage is optimal for this use case.

---

### 6. Billing Handoff & Retry Queue

**Service:** `create_billing_handoff()`, `send_billing_handoff()`  
**File:** [backend/apps/core/services.py](backend/apps/core/services.py#L750-L850)

**Query Pattern:**
```python
# Fetch pending handoffs with exponential backoff
handoff = BillingHandoff.objects.filter(
    status='PENDING',
    next_retry_at__lte=now()
).select_for_update().first()
```

**Expected Performance:**
| Scenario | Pending Count | Query Time |
|----------|--------------|-----------|
| Normal (<10 pending) | 5 | 5 ms |
| Backlog (50-100 pending) | 50 | 20 ms |
| Stuck queue (1000+ pending) | 1000 | 100+ ms |

**Recommended Indexes:**
```sql
CREATE INDEX idx_billing_status_retry 
  ON core_billinghandoff(status, next_retry_at);
CREATE INDEX idx_billing_created_at 
  ON core_billinghandoff(created_at DESC);
```

**Optimization Strategies:**
1. Implement separate billing worker service
2. Use Redis queue for faster FIFO processing
3. Implement dead-letter queue (DLQ) for failed items
4. Clean up old completed handoffs (archive after 180 days)

**Current Status:** ✅ Good. Retry logic with exponential backoff is efficient.

---

### 7. Daily Metrics Dashboard Query

**Service:** `daily_kpi_metrics()`  
**File:** [backend/apps/core/services.py](backend/apps/core/services.py#L1050-L1150)

**Query Pattern:**
```python
# Aggregate metrics for dashboard
metrics = Appointment.objects.filter(
    slot_date=date,
    specialty=specialty
).aggregate(
    total_volume=Count('id'),
    completed_count=Count('id', filter=Q(status='COMPLETED')),
    avg_wait_time=Avg(F('queue__wait_time_minutes')),
    no_show_count=Count('id', filter=Q(status='NO_SHOW'))
)
```

**Expected Performance:**
| Query Type | Record Count | Query Time |
|-----------|-------------|-----------|
| Single doctor, 1 day | 30 records | 10 ms |
| Full specialty, 1 day | 500 records | 50 ms |
| Hospital-wide, 1 day | 5000+ records | 200-500 ms |
| Date range (7 days) | 35000+ records | 1000+ ms |

**Recommended Indexes:**
```sql
CREATE INDEX idx_appointment_date_specialty 
  ON core_appointment(slot_date, specialty);
CREATE INDEX idx_appointment_status 
  ON core_appointment(status);
CREATE INDEX idx_queue_wait_time 
  ON core_queueitem(wait_time_minutes);
```

**Optimization Strategies:**
1. **Materialized Views:** Pre-aggregate daily metrics in background
2. **Caching:** Cache daily metrics for 1 hour
3. **Time-series DB:** Consider InfluxDB for time-series metrics
4. **Background Worker:** Calculate at EOD, not on-demand

**Implementation Example:**
```python
# Background task (Celery)
@app.task
def calculate_daily_metrics(date):
    """Run at 6 PM daily to aggregate metrics"""
    metrics = Appointment.objects.filter(slot_date=date).aggregate(...)
    cache.set(f'metrics_{date}', metrics, timeout=86400)  # 24 hour cache
```

**Current Status:** ⚠️ Medium. Needs optimization for multi-day range queries.

---

### 8. Report Export Query

**Service:** `generate_report_export()`  
**File:** [backend/apps/core/services.py](backend/apps/core/services.py#L1200-1250)

**Query Pattern:**
```python
# Fetch all data for date range and format to CSV
appointments = Appointment.objects.filter(
    slot_date__range=[start_date, end_date],
    **filters
).select_related('patient', 'doctor', 'consultation')

# Generate CSV in memory
csv_content = generate_csv(appointments)
```

**Expected Performance:**
| Report Scope | Records | Query Time | Generation Time | Total |
|-------------|---------|-----------|-----------------|-------|
| Daily report | 100 records | 20 ms | 100 ms | 120 ms |
| Weekly report | 700 records | 100 ms | 500 ms | 600 ms |
| Monthly report | 3000 records | 400 ms | 2000 ms | 2400 ms |

**Optimization Strategies:**
1. **Async Processing:** Generate reports in background worker
2. **Pagination:** Return results in chunks (avoid loading entire dataset)
3. **Streaming:** Stream CSV output to avoid memory buffering
4. **Database Cursor:** Use server-side cursors for large datasets
5. **Index:** Add index on (slot_date, status)

**Recommended Implementation:**
```python
# Async report generation (Celery)
@app.task
def generate_report_async(user_id, filters):
    """Generate report asynchronously, notify user when ready"""
    export = ReportExport.objects.create(
        format='CSV', status='GENERATING', generated_by_id=user_id
    )
    
    # Fetch data in chunks
    for chunk in Appointment.objects.filter(**filters).iterator(chunk_size=1000):
        # Process and write chunk to file
        pass
    
    export.status = 'COMPLETED'
    export.save()
    notify_user(user_id, f'Report ready: {export.artifact_path}')
```

**Current Status:** ⚠️ Medium. Acceptable for clinic usage, needs optimization for hospital-wide reports.

---

## Database Indexing Strategy

### Current Indexes (From Migrations)

Django automatically creates:
- Primary key (pk) on all models
- Foreign key indexes on `_id` fields
- Unique constraints

### Recommended Additional Indexes

**Priority 1 (Critical):**
```sql
-- Patient search
CREATE INDEX idx_patient_phone ON core_patient(phone);
CREATE INDEX idx_patient_dob ON core_patient(dob);

-- Appointment booking
CREATE INDEX idx_appointment_doctor_date_status 
  ON core_appointment(doctor_id, slot_date, status);

-- Queue operations
CREATE INDEX idx_queue_date_location 
  ON core_queueitem(created_at, appointment_id);
```

**Priority 2 (Important):**
```sql
-- Consultation/vitals
CREATE INDEX idx_consultation_appointment 
  ON core_consultation(appointment_id);
CREATE INDEX idx_vitals_consultation 
  ON core_vitals(consultation_id);

-- Billing operations
CREATE INDEX idx_billing_status_retry 
  ON core_billinghandoff(status, next_retry_at);

-- Metrics
CREATE INDEX idx_appointment_date_specialty 
  ON core_appointment(slot_date, specialty);
```

**Priority 3 (Nice-to-have):**
```sql
-- Historical queries
CREATE INDEX idx_appointment_created_at 
  ON core_appointment(created_at DESC);
  
-- Audit trail
CREATE INDEX idx_amendment_consultation 
  ON core_consultationamendment(consultation_id);
```

### Migration to Apply Indexes

```python
# Create migration
# python manage.py makemigrations core --empty --name add_performance_indexes

from django.db import migrations

class Migration(migrations.Migration):
    operations = [
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS idx_patient_phone ON core_patient(phone);",
            reverse_sql="DROP INDEX IF EXISTS idx_patient_phone;"
        ),
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS idx_patient_dob ON core_patient(dob);",
            reverse_sql="DROP INDEX IF EXISTS idx_patient_dob;"
        ),
        # ... additional indexes
    ]
```

---

## Query Profiling Recommendations

### Enable Django Query Logging

**Development:**
```python
# settings/development.py
LOGGING = {
    'version': 1,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'django.db.backends': {
            'level': 'DEBUG',
            'handlers': ['console'],
        },
    },
}
```

### Monitor Slow Queries in Tests

```python
# tests/conftest.py
import logging
from django.test.utils import CaptureQueriesContext
from django.test import TestCase

class SlowQueryTest(TestCase):
    def test_patient_search_performance(self):
        with CaptureQueriesContext(connection) as ctx:
            patients = search_patients(phone="9876543210")
        
        # Assert query count
        assert len(ctx.captured_queries) < 5, "Too many queries"
        
        # Assert query time
        total_time = sum(
            float(q['time']) for q in ctx.captured_queries
        )
        assert total_time < 0.1, f"Queries took {total_time}s"
```

### Production Monitoring (PostgreSQL)

```sql
-- Enable slow query logging
-- postgresql.conf
log_min_duration_statement = 100  # Log queries > 100ms

-- Check slow queries
SELECT query, calls, mean_exec_time 
FROM pg_stat_statements 
WHERE mean_exec_time > 100 
ORDER BY mean_exec_time DESC;

-- Monitor index usage
SELECT schemaname, tablename, indexname, idx_scan 
FROM pg_stat_user_indexes 
WHERE idx_scan = 0;  -- Unused indexes
```

---

## Caching Strategy

### Multi-Level Caching Architecture

```
Request
  ↓
[1] Django ORM Cache (QuerySet level)
  ├─ Cache key: f'appointment_{appointment_id}'
  ├─ TTL: 5 minutes
  └─ Invalidate on: save/delete
  ↓
[2] Redis Cache (Application level)
  ├─ Queue board: 5 seconds
  ├─ Patient search: 10 minutes
  ├─ Doctor schedule: 30 minutes
  └─ Daily metrics: 1 hour
  ↓
[3] Browser Cache (HTTP level)
  ├─ Static assets: 1 year (versioned)
  ├─ API responses: max-age=0, must-revalidate
  └─ HTML: no-cache
  ↓
Database
```

### Implementation Example

```python
# services.py
from django.core.cache import cache

def list_queue_board(slot_date, location):
    cache_key = f'queue_board_{slot_date}_{location}'
    cached = cache.get(cache_key)
    
    if cached:
        return cached
    
    queue_items = QueueItem.objects.filter(
        appointment__slot_date=slot_date,
        appointment__location=location
    ).select_related('patient', 'appointment__doctor')
    
    result = serialize(queue_items)
    cache.set(cache_key, result, timeout=300)  # 5 min
    return result

# Invalidate on update
def queue_action(queue_item_id, action):
    queue_item.status = action
    queue_item.save()
    
    # Invalidate cache
    cache.delete(f'queue_board_{queue_item.appointment.slot_date}_{location}')
```

---

## Production Database Configuration

### PostgreSQL Optimization (production)

```ini
# postgresql.conf
shared_buffers = 256MB           # 25% of RAM for 1GB system
effective_cache_size = 1GB       # 75% of RAM
work_mem = 10MB                  # RAM/max_connections
maintenance_work_mem = 64MB      # 16% of RAM

max_connections = 100            # Clinic typical: 20-50
max_wal_size = 4GB              # For frequent writes

# Query planning
random_page_cost = 1.1           # SSD preferred
effective_io_concurrency = 200   # For SSD

# Logging
log_min_duration_statement = 100  # Log slow queries (>100ms)
log_statement = 'all'            # Development only
```

### Connection Pooling (PgBouncer)

```ini
# pgbouncer.ini
[databases]
opd_db = host=localhost port=5432 dbname=opd_management

[pgbouncer]
pool_mode = transaction
max_client_conn = 500
default_pool_size = 25
reserve_pool_size = 5
```

---

## Monitoring Checklist

- [ ] Enable query logging in development
- [ ] Profile critical paths with `django-extensions` or `silk`
- [ ] Monitor slow query log in staging
- [ ] Create indexes per Priority 1 and 2
- [ ] Test index impact on queries
- [ ] Configure Redis for caching
- [ ] Monitor cache hit rates
- [ ] Set up PostgreSQL slow query alerts
- [ ] Document query patterns in runbooks
- [ ] Schedule quarterly index review

---

**Next Steps:**
1. Apply Priority 1 indexes in staging
2. Profile all API endpoints with realistic load
3. Establish baseline metrics for monitoring
4. Implement caching for queue board and metrics
5. Configure slow query alerting in production
