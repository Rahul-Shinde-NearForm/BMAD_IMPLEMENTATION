# OPD Management System - Network Performance Scenarios & API Testing Guide

**Generated:** April 29, 2026  
**Supplement to:** PERFORMANCE_ANALYSIS.md

---

## Network Condition Simulations

Based on the baseline performance metrics from localhost testing (LCP: 204 ms, TTFB: 4 ms), here are **projected performance metrics** under different network conditions:

### Scenario 1: Slow 3G (Primary scenario for clinic WiFi degradation)

**Network Profile:**
- Download: 400 Kbps
- Upload: 400 Kbps  
- Latency: 400 ms
- Packet loss: 2%

**Projected Metrics:**
```
Baseline (WiFi):     TTFB: 4 ms    | LCP: 204 ms   | Total: 204 ms
Slow 3G Scaled:      TTFB: 100 ms  | LCP: 500-700 ms | Total: 500-700 ms
Impact Factor:       25x latency   | 2.5-3.5x render delay
```

**Performance Breakdown:**
| Phase | Baseline | Slow 3G | Delta |
|-------|----------|---------|-------|
| Network Latency | 0 ms | 400 ms | +400 ms |
| DNS + TCP | 4 ms | 60 ms | +56 ms |
| HTTP Request | 1 ms | 50 ms | +49 ms |
| Response Transfer | 1 ms | 20 ms | +19 ms |
| Rendering | 198 ms | 200 ms | +2 ms |
| **Total LCP** | **204 ms** | **730 ms** | **+526 ms** |

**Status:** ⚠️ Acceptable but noticeable. Single page load in ~0.7 seconds.

---

### Scenario 2: Fast 4G / LTE (Typical clinic WiFi with good signal)

**Network Profile:**
- Download: 4 Mbps
- Upload: 3 Mbps
- Latency: 50 ms
- Packet loss: 0%

**Projected Metrics:**
```
Baseline (WiFi):     TTFB: 4 ms    | LCP: 204 ms   | Total: 204 ms
Fast 4G Scaled:      TTFB: 15 ms   | LCP: 250 ms   | Total: 250 ms
Impact Factor:       3.75x latency | 1.2x render delay
```

**Status:** ✓ Good. Nearly imperceptible difference from WiFi.

---

### Scenario 3: Slow 4G (Degraded clinic WiFi or mobile hotspot)

**Network Profile:**
- Download: 1.6 Mbps
- Upload: 750 Kbps
- Latency: 400 ms
- Packet loss: 1%

**Projected Metrics:**
```
Baseline (WiFi):     TTFB: 4 ms    | LCP: 204 ms   | Total: 204 ms
Slow 4G Scaled:      TTFB: 150 ms  | LCP: 400 ms   | Total: 400 ms
Impact Factor:       37.5x latency | 2x render delay
```

**Status:** ✓ Acceptable. Page loads in ~0.4 seconds.

---

## API Response Time Testing

### Critical Paths to Monitor

#### 1. **Patient Search** (Receptionist workflow)

**Endpoint:** `POST /api/patients/search/`

**Request Payload:**
```json
{
  "phone": "9876543210",
  "dob": "1990-01-15"
}
```

**Expected Response Times (by network):**
- WiFi: 20-50 ms
- 4G: 100-200 ms
- 3G: 300-500 ms

**Performance Goal:** < 200 ms p95

**Test Query:**
```bash
# Test with time measurement
curl -w "Total: %{time_total}s\n" \
  -X POST http://localhost:8000/api/patients/search/ \
  -H "Content-Type: application/json" \
  -d '{"phone": "9876543210", "dob": "1990-01-15"}'
```

---

#### 2. **Appointment Booking** (Receptionist workflow)

**Endpoint:** `POST /api/appointments/book/`

**Request Payload:**
```json
{
  "patient_id": 1,
  "doctor_id": 2,
  "slot_date": "2026-04-30",
  "start_time": "09:00",
  "end_time": "09:30",
  "visit_type": "NEW"
}
```

**Expected Response Times:**
- WiFi: 50-100 ms
- 4G: 150-250 ms
- 3G: 400-700 ms

**Performance Goal:** < 300 ms p95

**Database Operations:**
- Check appointment conflicts (index on doctor, slot_date, start_time)
- Insert appointment record
- Generate OPD number
- Fetch patient history

**Optimization:** Pre-generate OPD numbers in background if batch operations

---

#### 3. **Prescription Issue** (Doctor workflow)

**Endpoint:** `POST /api/consultations/{id}/prescription/issue/`

**Request Payload:**
```json
{
  "items": [
    {
      "drug": "Paracetamol",
      "dosage_form": "Tablet",
      "strength": "500 mg",
      "dose": "1",
      "frequency": "BD",
      "duration": "5 days",
      "timing": "after_food",
      "route": "oral",
      "instructions": "With water after meals"
    }
  ],
  "doctor_qualification": "MD (Internal Medicine)",
  "doctor_reg_number": "MCI123456",
  "clinic_name": "City Hospital OPD",
  "clinic_address": "123 Main Street, City, State",
  "special_instructions": "Follow-up in 1 week",
  "validity_days": 30
}
```

**Expected Response Times:**
- WiFi: 30-60 ms
- 4G: 100-150 ms
- 3G: 300-500 ms

**Performance Goal:** < 200 ms p95

**Database Operations:**
- Validate consultation exists
- Insert prescription record
- Generate RX number
- Create audit log entry

---

#### 4. **Queue Board Sync** (Doctor workflow)

**Endpoint:** `GET /api/queue/board/?slot_date=2026-04-30&location=OPD_A`

**Expected Response Times:**
- WiFi: 20-50 ms
- 4G: 100-150 ms
- 3G: 300-400 ms

**Performance Goal:** < 200 ms p95

**Database Operations:**
- Fetch all appointments for date/location
- Fetch queue items with transitions
- Fetch patient names (join)
- Compute wait times

**Optimization:** Cache queue board for 10 seconds if high frequency polling

---

#### 5. **Dashboard Metrics** (Admin workflow)

**Endpoint:** `GET /api/reports/dashboard/daily-metrics/?date=2026-04-29`

**Expected Response Times:**
- WiFi: 100-500 ms (depends on query complexity)
- 4G: 300-1000 ms
- 3G: 1000-3000 ms

**Performance Goal:** < 2000 ms p95 (aggregation queries are slower)

**Database Operations:**
- Sum appointments by doctor
- Average wait times
- Calculate no-show rates
- Count completed appointments
- Aggregate billing handoffs

**Optimization:**
1. Add database indexes on created_at, status
2. Consider materialized views for daily aggregation
3. Cache results for 5 minutes
4. Run aggregation in background worker if > 500 ms

---

## Load Testing Scenarios

### Scenario 1: Morning Rush (Peak Load)

**Time:** 8:00 AM - 10:00 AM (typical clinic opening rush)

**Concurrent Users:**
- 3 Receptionists (patient registration, booking)
- 2 Doctors (consultations, prescriptions)
- 1 Pharmacist (order fulfillment)
- 1 Admin (monitoring dashboard)

**Expected Load:**
- 7 concurrent sessions
- ~50 HTTP requests per minute
- ~5 database transactions per second

**Test Script (pseudo-code):**
```python
# Receptionist (3x concurrent)
while True:
    patient = search_patient(phone_number)  # 30 ms
    time.sleep(random(10, 30))  # User reading
    appointment = book_appointment(patient_id, doctor_id)  # 50 ms
    time.sleep(random(20, 60))  # User navigation
    
# Doctor (2x concurrent)  
while True:
    appointments = fetch_today_appointments(doctor_id)  # 50 ms
    time.sleep(random(30, 120))  # Consultation
    consultation = finalize_consultation(appt_id)  # 60 ms
    prescription = issue_prescription(consultation_id)  # 30 ms
    time.sleep(random(60, 300))  # Next patient
```

**Expected Results:**
- All API endpoints respond < 200 ms p95
- Database query time < 100 ms p95
- No timeouts or errors
- CPU usage < 60%
- Memory usage < 70%

---

### Scenario 2: Full Day Operations (Sustained Load)

**Duration:** 9 AM - 5 PM (8 hours)

**User Distribution:**
```
Time       Receptionists  Doctors  Pharmacists  Admins
9-10 AM         3          2          1           1      (peak)
10-12 PM        2          2          1           0      (steady)
12-1 PM         1          1          1           0      (lunch)
1-3 PM          2          2          1           0      (steady)
3-5 PM          2          2          1           1      (dashboard)
```

**Expected Metrics:**
- Average response time: 50-100 ms
- p95 response time: 150-200 ms
- p99 response time: 300-500 ms
- Error rate: < 0.1%

---

### Scenario 3: Weekend/Off-Hours (Minimal Load)

**Concurrent Users:** 1 doctor + 1 receptionist (emergency clinic)

**Expected Metrics:**
- Response time: 20-30 ms (no contention)
- Database idle most of time
- CPU: < 5%
- Memory: ~500 MB (baseline)

---

## Performance Baseline Thresholds

**Green (Good):** Page load complete
| Metric | Threshold | Status |
|--------|-----------|--------|
| TTFB | < 200 ms | ✅ 4 ms |
| LCP | < 2.5 s | ✅ 204 ms |
| FCP | < 1.8 s | ✅ 4 ms |
| CLS | < 0.1 | ✅ 0.00 |
| API Response (p95) | < 200 ms | ⏳ Test needed |
| Database Query (p95) | < 100 ms | ⏳ Test needed |

---

## Load Test Tools Recommendations

### For Local Network Testing

```bash
# Option 1: Apache Bench (simple, built-in on macOS)
ab -n 100 -c 5 http://localhost:8000/login/

# Option 2: wrk (fast, low-overhead)
wrk -t4 -c5 -d30s http://localhost:8000/login/

# Option 3: Locust (Python-based, realistic scenarios)
# Install: pip install locust
locust -f locustfile.py --host=http://localhost:8000
```

### For API Testing with Realistic Payloads

```python
# Locust script example (locustfile.py)
from locust import HttpUser, task, between

class OPDUser(HttpUser):
    wait_time = between(5, 15)
    
    @task(3)
    def search_patients(self):
        self.client.post("/api/patients/search/",
            json={"phone": "9876543210", "dob": "1990-01-15"})
    
    @task(2)
    def book_appointment(self):
        self.client.post("/api/appointments/book/",
            json={"patient_id": 1, "doctor_id": 2, 
                  "slot_date": "2026-04-30", "start_time": "09:00"})
    
    @task(1)
    def view_queue(self):
        self.client.get("/api/queue/board/?slot_date=2026-04-30")
```

---

## Monitoring Checklist for Production

- [ ] Set up APM (Application Performance Monitoring) agent
- [ ] Configure slow query logging (threshold: 100 ms)
- [ ] Enable request/response time metrics in Django
- [ ] Set up alerts for:
  - API latency > 500 ms p95
  - Error rate > 1%
  - Database connection pool > 80%
  - Server CPU > 80%
  - Memory usage > 85%
- [ ] Create dashboards for:
  - Request latency trends
  - Error rates by endpoint
  - Database performance
  - Resource utilization
- [ ] Schedule weekly performance reviews
- [ ] Maintain performance budget (LCP < 2.5s, API < 200ms p95)

---

## Continuous Performance Improvement Process

1. **Weekly:** Review slow query log, API latency metrics
2. **Monthly:** Run load test with current user volume
3. **Quarterly:** Profile full user workflows for bottlenecks
4. **Annually:** Capacity planning, upgrade assessment

---

**Next Steps:**
1. Execute load testing scenarios using Locust
2. Profile API endpoints under peak load
3. Identify slowest database queries
4. Implement caching where beneficial
5. Document results and update this guide
