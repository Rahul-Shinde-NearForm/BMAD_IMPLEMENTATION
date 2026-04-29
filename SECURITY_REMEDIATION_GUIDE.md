# Security Review - Remediation Implementation Guide

**Generated:** April 29, 2026  
**Purpose:** Step-by-step fix guide for identified security issues  
**Estimated Implementation Time:** 2 hours

---

## Quick Reference: Issues by Priority

| Priority | Issue | File | Fix Time | Status |
|----------|-------|------|----------|--------|
| 🔴 CRITICAL | DEBUG = True | settings.py | 5 min | Apply immediately |
| 🔴 CRITICAL | SECRET_KEY exposed | settings.py | 10 min | Apply immediately |
| 🟠 MEDIUM | ALLOWED_HOSTS | settings.py | 10 min | Before production |
| 🟠 MEDIUM | Security headers | settings.py | 15 min | Before production |
| 🟠 MEDIUM | Query validation | views.py | 20 min | Before production |
| 🟡 LOW | Data exposure | views.py | 10 min | Optional, nice-to-have |

---

## Fix #1: DEBUG Setting (CRITICAL)

### Current Code
**File:** `backend/config/settings.py` (line 27)
```python
DEBUG = True
```

### Remediation
```python
import os

# Get DEBUG from environment variable, default to False for safety
DEBUG = os.environ.get('DJANGO_DEBUG', 'False').lower() == 'true'

# Alternative: use django-environ for cleaner code
# pip install django-environ
# from environ import Env
# env = Env()
# DEBUG = env.bool('DJANGO_DEBUG', default=False)
```

### How to Deploy
```bash
# In development environment:
export DJANGO_DEBUG=True
python manage.py runserver

# In production environment:
# DON'T set DJANGO_DEBUG (or set to False)
python manage.py runserver  # Will use DEBUG=False
```

### Verification
```bash
# Verify setting is correct
python manage.py shell
>>> from django.conf import settings
>>> print(settings.DEBUG)
False  # Should be False in production
```

---

## Fix #2: SECRET_KEY Exposure (CRITICAL)

### Current Code
**File:** `backend/config/settings.py` (line 23)
```python
SECRET_KEY = 'django-insecure-m22-cn$_)!(+qk$6vhfrd0wd8&s((*s-(3xh@$d-w3ox=*#5$o'
```

### Remediation - Method 1: Environment Variable
```python
import os

SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY')

if not SECRET_KEY:
    if os.environ.get('ENVIRONMENT', 'development') == 'production':
        raise ValueError(
            'DJANGO_SECRET_KEY environment variable is required in production. '
            'Generate with: python -c "from django.core.management.utils import '
            'get_random_secret_key; print(get_random_secret_key())"'
        )
    # Use a placeholder in development (will be overridden by env var if set)
    SECRET_KEY = 'django-insecure-development-key-change-in-production'
```

### Remediation - Method 2: Using python-decouple (Recommended)
```bash
# Install python-decouple
pip install python-decouple
```

```python
from decouple import config, UndefinedValueError

try:
    SECRET_KEY = config('DJANGO_SECRET_KEY')
except UndefinedValueError:
    if config('ENVIRONMENT', default='development') == 'production':
        raise ValueError('DJANGO_SECRET_KEY required in production')
    SECRET_KEY = 'django-insecure-development-key'
```

### How to Generate & Deploy

**Step 1: Generate a new secret key**
```bash
python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'
# Output example:
# a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4
```

**Step 2: Store in environment**
```bash
# On server, add to .env file (NOT in version control):
echo "DJANGO_SECRET_KEY=a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4" > /opt/opd/.env

# Make sure it's not readable by others:
chmod 600 /opt/opd/.env

# Load in shell before running Django:
source /opt/opd/.env
python manage.py runserver
```

**Step 3: Use in systemd service (recommended)**
```ini
# /etc/systemd/system/opd.service
[Service]
Environment="DJANGO_SECRET_KEY=a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4"
Environment="DJANGO_DEBUG=False"
```

### Verification
```bash
# Test that the new key works
python manage.py check
# Should output: System check identified no issues (0 silenced).
```

---

## Fix #3: ALLOWED_HOSTS Configuration (MEDIUM)

### Current Code
**File:** `backend/config/settings.py` (line 30)
```python
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]
```

### Remediation
```python
import os

ENVIRONMENT = os.environ.get('ENVIRONMENT', 'development')

if ENVIRONMENT == 'production':
    # Clinic LAN deployment - add your clinic's network details
    ALLOWED_HOSTS = [
        'opd.clinic.local',           # Internal DNS (if configured)
        '192.168.1.100',              # Doctor workstation
        '192.168.1.101',              # Receptionist workstation
        '192.168.1.102',              # Pharmacist workstation
        '192.168.1.50',               # Backup/admin machine
        # Add actual IPs from your clinic network
    ]
    
    # Alternative: use wildcards for subnet if needed
    # ALLOWED_HOSTS = ['192.168.1.*', 'opd.clinic.local']
    
elif ENVIRONMENT == 'staging':
    ALLOWED_HOSTS = [
        'opd-staging.clinic.local',
        '192.168.1.200',  # Staging server IP
    ]
    
else:  # development
    ALLOWED_HOSTS = ['*']  # Allow all in development
```

### How to Deploy
1. **Identify your clinic network IPs:**
   ```bash
   # On each clinic machine, run:
   ipconfig  # Windows
   ifconfig  # Mac/Linux
   
   # Note down all machine IPs that will access the OPD server
   ```

2. **Update ALLOWED_HOSTS** with actual IPs

3. **Test:**
   ```bash
   # From each clinic machine, test:
   curl http://192.168.1.100:8000/
   curl http://opd.clinic.local:8000/  # If DNS is configured
   ```

---

## Fix #4: HTTP Security Headers (MEDIUM)

### Where to Add
**File:** `backend/config/settings.py` (at the end, before closing)

### Remediation Code
```python
# ============================================================================
# SECURITY HEADERS CONFIGURATION
# ============================================================================

if not DEBUG:  # Only apply strict security in production
    # HTTPS & Cookie Security
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    CSRF_COOKIE_HTTPONLY = True
    SESSION_COOKIE_HTTPONLY = True
    
    # HTTPS Strict Transport Security (HSTS)
    SECURE_HSTS_SECONDS = 31536000  # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    
    # Content Security Policy (CSP)
    SECURE_CONTENT_SECURITY_POLICY = {
        'default-src': ("'self'",),
        'script-src': ("'self'",),
        'style-src': ("'self'", "'unsafe-inline'"),  # Clinic UI needs inline styles
        'img-src': ("'self'", "data:", "https:"),
        'font-src': ("'self'",),
        'connect-src': ("'self'",),
        'frame-ancestors': ("'none'",),
        'base-uri': ("'self'",),
        'form-action': ("'self'",),
    }
    
    # X-Frame-Options - Prevent clickjacking
    X_FRAME_OPTIONS = 'DENY'
    
    # Additional security
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_HSTS_PRELOAD = True

else:  # Development settings
    SECURE_SSL_REDIRECT = False
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False
    # HSTS not needed in development
```

### Verification
```bash
# Test security headers
curl -I https://opd.clinic.local

# Should include:
# Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
# X-Frame-Options: DENY
# X-Content-Type-Options: nosniff
# Content-Security-Policy: ...
```

---

## Fix #5: Query Parameter Validation (MEDIUM)

### Current Code
**File:** `backend/apps/core/views.py` (around line 910)
```python
@login_required
@require_GET
@role_required("Admin")
def dashboard_daily_metrics(request):
    date_value = request.GET.get("date")
    specialty = request.GET.get("specialty")      # ⚠️ No validation
    doctor_id = request.GET.get("doctor_id")      # ⚠️ Checked too late
    location = request.GET.get("location")        # ⚠️ No validation
    # ... rest
```

### Remediation
```python
# Add at the top of views.py (after imports)
VALID_SPECIALTIES = ['Cardiology', 'Orthopedics', 'Dermatology', 'General', 'Pediatrics']
VALID_LOCATIONS = ['OPD_A', 'OPD_B', 'OPD_C', 'OPD_D']

# Then update the view:
@login_required
@require_GET
@role_required("Admin")
def dashboard_daily_metrics(request):
    # Validate date
    date_value = request.GET.get("date")
    try:
        report_date = datetime.strptime(date_value, "%Y-%m-%d").date() if date_value else None
    except ValueError:
        return JsonResponse({"error": "invalid_date_format", "expected": "YYYY-MM-DD"}, status=400)
    
    if report_date is None:
        from django.utils import timezone
        report_date = timezone.localdate()
    
    # Validate specialty
    specialty = request.GET.get("specialty", "").upper()
    if specialty and specialty not in VALID_SPECIALTIES:
        return JsonResponse(
            {"error": "invalid_specialty", "valid_options": VALID_SPECIALTIES},
            status=400
        )
    
    # Validate doctor_id (convert and validate early)
    doctor_id = request.GET.get("doctor_id")
    if doctor_id is not None:
        try:
            doctor_id = int(doctor_id)
            if doctor_id <= 0:
                raise ValueError
        except ValueError:
            return JsonResponse({"error": "invalid_doctor_id"}, status=400)
    
    # Validate location
    location = request.GET.get("location", "").upper()
    if location and location not in VALID_LOCATIONS:
        return JsonResponse(
            {"error": "invalid_location", "valid_options": VALID_LOCATIONS},
            status=400
        )
    
    # Now safe to call service
    data = daily_kpi_metrics(
        report_date=report_date,
        specialty=specialty,
        doctor_id=doctor_id,
        location=location,
    )
    return JsonResponse(data)
```

### Verification
```bash
# Test with valid parameters:
curl "http://localhost:8000/api/reports/dashboard/daily-metrics/?specialty=Cardiology&location=OPD_A"
# Should return metrics

# Test with invalid parameters:
curl "http://localhost:8000/api/reports/dashboard/daily-metrics/?specialty=InvalidSpecialty"
# Should return 400 error

curl "http://localhost:8000/api/reports/dashboard/daily-metrics/?doctor_id=abc"
# Should return 400 error
```

---

## Fix #6: Patient Data Exposure (LOW - Optional)

### Current Code
**File:** `backend/apps/core/views.py` (around line 760)
```python
def prescription_get(request, consultation_id):
    # ...
    return JsonResponse({
        "patient": {
            "name": f"{patient.first_name} {patient.last_name}",
            "phone": patient.phone,  # ⚠️ Always exposed
        },
    })
```

### Remediation (Optional - nice-to-have)
```python
@require_GET
@login_required
@role_required("Doctor", "Pharmacist", "Admin")
def prescription_get(request, consultation_id):
    try:
        p = Prescription.objects.select_related("patient", "doctor", "consultation").get(consultation_id=consultation_id)
    except Prescription.DoesNotExist:
        return JsonResponse({"error": "not_found"}, status=404)

    patient = p.patient
    doctor = p.doctor
    consultation = p.consultation
    
    # Only show phone to prescribing doctor or admin
    show_phone = (
        request.user.id == doctor.id or 
        request.user.is_superuser or
        'Admin' in [g.name for g in request.user.groups.all()]
    )
    
    # Indian prescription format response
    return JsonResponse({
        # --- Header ---
        "rx_number": p.rx_number,
        "issued_at": p.issued_at.strftime("%d/%m/%Y %H:%M"),
        "validity_days": p.validity_days,
        "doctor": {
            "name": doctor.full_name,
            "specialty": doctor.specialty,
            "qualification": p.doctor_qualification,
            "reg_number": p.doctor_reg_number,
        },
        "clinic": {
            "name": p.clinic_name,
            "address": p.clinic_address,
        },
        # --- Patient Section ---
        "patient": {
            "name": f"{patient.first_name} {patient.last_name}",
            "age": p.patient_age_at_issue,
            "sex": patient.get_gender_display(),
            "weight_kg": str(p.patient_weight_kg) if p.patient_weight_kg else None,
            "phone": patient.phone if show_phone else None,  # Only if authorized
        },
        # ... rest of response
    })
```

---

## Deployment Checklist

### Pre-Deployment
- [ ] Apply Fix #1 (DEBUG = True)
- [ ] Apply Fix #2 (SECRET_KEY)
- [ ] Generate new SECRET_KEY
- [ ] Update ALLOWED_HOSTS with clinic IPs
- [ ] Apply Fix #3 (Security headers)
- [ ] Apply Fix #4 (Query validation)
- [ ] Test locally with all fixes applied
- [ ] Run Django security checks

### At Deployment
```bash
# Run all checks
python manage.py check --deploy

# Expected output:
# System check identified no issues (0 silenced).

# Test each clinic machine can access:
curl http://192.168.1.100:8000/
curl http://opd.clinic.local:8000/

# Verify headers:
curl -I https://opd.clinic.local
```

### Post-Deployment
- [ ] Verify DEBUG = False in production
- [ ] Test login/logout works
- [ ] Test all roles can access their workbenches
- [ ] Verify CSRF protection works
- [ ] Monitor error logs for configuration issues
- [ ] Schedule security review (1 week post-launch)

---

## Automated Testing

### Run Security Checks
```bash
# Install security tools
pip install bandit
pip install safety
pip install django-defender  # For brute-force protection

# Run checks
bandit -r backend/apps/
safety check
python manage.py check --deploy
```

### Test CSRF Protection
```bash
# Create test script
cat > test_csrf.sh << 'EOF'
# This should fail (no CSRF token)
curl -X POST http://localhost:8000/api/patients/register/ \
  -d "first_name=Test&last_name=User" 2>/dev/null | grep -i "csrf"

# Output should contain error about CSRF token
EOF

chmod +x test_csrf.sh
./test_csrf.sh
```

---

## Summary of Changes

| File | Change | Lines Changed |
|------|--------|----------------|
| settings.py | DEBUG = environment var | 1 |
| settings.py | SECRET_KEY = environment var | 1 |
| settings.py | ALLOWED_HOSTS = clinic IPs | 1 |
| settings.py | Add security headers | 30 |
| views.py | Validate specialty, location, doctor_id | 20 |
| views.py | (Optional) Restrict phone visibility | 5 |

**Total lines changed:** ~58 lines (mostly additions)

---

## Rollback Plan

If any issues occur:

```bash
# Revert to previous settings.py
git checkout HEAD -- backend/config/settings.py

# Revert to previous views.py (if changed)
git checkout HEAD -- backend/apps/core/views.py

# Restart service
systemctl restart opd.service
```

---

## Testing Queries

### Test Valid Requests
```bash
# Valid specialty and location
curl "http://localhost:8000/api/reports/dashboard/daily-metrics/?specialty=Cardiology&location=OPD_A&date=2026-04-29"

# Valid doctor_id only
curl "http://localhost:8000/api/reports/dashboard/daily-metrics/?doctor_id=1"

# Valid date only
curl "http://localhost:8000/api/reports/dashboard/daily-metrics/?date=2026-04-29"
```

### Test Invalid Requests (should return 400)
```bash
# Invalid specialty
curl "http://localhost:8000/api/reports/dashboard/daily-metrics/?specialty=INVALID"
# Expected: {"error": "invalid_specialty", ...}

# Invalid doctor_id
curl "http://localhost:8000/api/reports/dashboard/daily-metrics/?doctor_id=notanumber"
# Expected: {"error": "invalid_doctor_id"}

# Invalid date format
curl "http://localhost:8000/api/reports/dashboard/daily-metrics/?date=2026/04/29"
# Expected: {"error": "invalid_date_format", ...}
```

---

**Implementation Guide Complete**  
**Ready for deployment after applying the critical fixes above**
