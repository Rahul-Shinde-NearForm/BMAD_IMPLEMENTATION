# Docker Best Practices & Architecture Guide

**OPD Management System - Containerization Standards**

---

## 📚 Table of Contents

1. [Dockerfile Architecture](#dockerfile-architecture)
2. [Multi-Stage Builds](#multi-stage-builds)
3. [Security Practices](#security-practices)
4. [Health Checks](#health-checks)
5. [Network Configuration](#network-configuration)
6. [Volume Management](#volume-management)
7. [Performance Optimization](#performance-optimization)
8. [Monitoring & Debugging](#monitoring--debugging)

---

## 🏗️ Dockerfile Architecture

### Backend Dockerfile (Django/Python)

**Key Features:**
- **Two-stage build:** Separates dependencies from runtime
- **Non-root user:** `django` user for security
- **Minimal base image:** `python:3.11-slim` (~150MB base)
- **Health checks:** HTTP endpoint monitoring
- **Production WSGI:** Gunicorn server configuration

```dockerfile
# Stage 1: Builder - installs dependencies
FROM python:3.11-slim as builder
RUN python -m venv /opt/venv
COPY requirements.txt .
RUN pip install -r requirements.txt

# Stage 2: Runtime - only includes runtime dependencies
FROM python:3.11-slim
COPY --from=builder /opt/venv /opt/venv
USER django  # Non-root user
HEALTHCHECK CMD curl -f http://localhost:8000/health/
CMD ["gunicorn", "config.wsgi:application"]
```

**Size Comparison:**
- Single-stage build: ~800MB
- Multi-stage build: ~350MB
- Reduction: ~56%

### Frontend Dockerfile (Nginx)

**Key Features:**
- **Nginx base:** Official `nginx:1.25-alpine` (~45MB)
- **Static asset serving:** Optimized with caching
- **Non-root user:** `nginx` user (default)
- **Security headers:** Built into Nginx config
- **Reverse proxy:** Proxies API requests to backend

```dockerfile
FROM node:18-alpine as builder
# Build stage (if needed)

FROM nginx:1.25-alpine
COPY docker/nginx.conf /etc/nginx/nginx.conf
USER nginx  # Nginx runs as non-root by default
HEALTHCHECK CMD curl -f http://localhost/health
```

---

## 🔧 Multi-Stage Builds

### Why Multi-Stage?

**Problem:** Docker images include everything - build tools, dependencies, source code

**Solution:** Use multiple stages, copy only runtime requirements

### Example: Backend

```dockerfile
# STAGE 1: Builder (220MB)
FROM python:3.11-slim as builder
RUN apt-get install build-essential libpq-dev  # ~200MB of build tools
RUN python -m venv /opt/venv
RUN pip install -r requirements.txt  # compiles packages

# STAGE 2: Runtime (35MB base + 100MB venv)
FROM python:3.11-slim
COPY --from=builder /opt/venv /opt/venv  # Only copy venv
# Build tools NOT included in final image!

# Result: 135MB final image instead of 350MB
```

### Best Practices for Multi-Stage

1. **Name stages clearly:**
   ```dockerfile
   FROM node:18-alpine as dependencies
   FROM node:18-alpine as builder
   FROM nginx:1.25-alpine as runtime
   ```

2. **Copy only what's needed:**
   ```dockerfile
   # Good - specific files
   COPY --from=builder /app/dist /usr/share/nginx/html
   
   # Bad - copies entire stage
   COPY --from=builder / /
   ```

3. **Set ownership for security:**
   ```dockerfile
   COPY --from=builder --chown=node:node /app/node_modules /app/node_modules
   ```

4. **Use appropriate base images:**
   - `python:3.11-slim` - Python (150MB)
   - `python:3.11-alpine` - Minimal Python (50MB, may need build-base)
   - `nginx:1.25-alpine` - Nginx (45MB)
   - `node:18-alpine` - Node.js (180MB)

---

## 🔒 Security Practices

### Non-Root Users

**Why:** Prevents privilege escalation attacks

**Implementation:**

```dockerfile
# Create user (do this in Dockerfile, not image)
RUN groupadd -r django && useradd -r -g django django

# Set ownership
COPY --chown=django:django /app /app

# Switch user
USER django

# Verify
CMD ["id"]  # Output: uid=1000(django) gid=1000(django)
```

### No Secrets in Image

**Wrong:**
```dockerfile
ENV DATABASE_PASSWORD=secret123  # ❌ Baked into image!
```

**Correct:**
```dockerfile
# Use at runtime
docker run -e DATABASE_PASSWORD=secret123 opd-backend

# Or with Docker Compose
services:
  backend:
    environment:
      DATABASE_PASSWORD: ${DB_PASSWORD}  # From .env file
```

### Minimal Base Images

**Image Size Comparison:**
```
ubuntu:latest          (~77MB)
python:3.11            (~900MB)
python:3.11-slim       (~150MB) ✓ Use this
python:3.11-alpine     (~50MB, but needs build-base)
scratch                (0MB, for compiled binaries only)
```

### Security Scanning

```bash
# Scan for vulnerabilities
docker scan opd-backend:latest
# or
trivy image opd-backend:latest

# Check for secrets in image
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
  aquasec/trivy image --scan-type secret opd-backend:latest
```

### File Permissions

```dockerfile
# Good - restrictive permissions
RUN chmod 755 /app
RUN chmod 600 /app/config/.env

# Bad - overly permissive
RUN chmod 777 /app

# Verify
RUN ls -la /app  # drwxr-xr-x (755 for directories)
```

---

## 💓 Health Checks

### Why Health Checks?

- **Orchestration:** Docker/K8s automatically restart unhealthy containers
- **Load Balancing:** Remove unhealthy instances from rotation
- **Monitoring:** Alert when services degrade
- **Rolling Updates:** Don't route traffic to starting containers

### Implementation

**Backend (Django):**

```dockerfile
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health/ || exit 1
```

**In views.py:**
```python
from django.http import JsonResponse

def health_check(request):
    """Simple health check endpoint"""
    return JsonResponse({"status": "healthy"})
```

**Frontend (Nginx):**

```dockerfile
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost/health || exit 1
```

**In nginx.conf:**
```nginx
location /health {
    access_log off;
    return 200 "healthy\n";
    add_header Content-Type text/plain;
}
```

### Health Check Parameters

| Parameter | Value | Meaning |
|-----------|-------|---------|
| `--interval` | 30s | Check every 30 seconds |
| `--timeout` | 10s | Allow 10s for check to complete |
| `--start-period` | 40s | Wait 40s before first check (app startup time) |
| `--retries` | 3 | Fail after 3 consecutive failures |

### Viewing Health Status

```bash
# Show health status
docker-compose ps

# Example output:
# NAME              STATUS
# opd-backend       Up 2 minutes (healthy)
# opd-frontend      Up 2 minutes (healthy)
# opd-db            Up 2 minutes (healthy)

# Check specific container health
docker inspect --format='{{json .State.Health}}' opd-backend | jq

# Output:
# {
#   "Status": "healthy",
#   "FailingStreak": 0,
#   "Rechecks": 8,
#   "LastCheck": "2026-04-29T10:30:45Z"
# }
```

---

## 🌐 Network Configuration

### Docker Network Architecture

```
┌─────────────────────────────────────┐
│     Docker Host Network Space       │
├─────────────────────────────────────┤
│                                     │
│  opd_network (bridge)               │
│  ├── backend (172.18.0.2:8000)      │
│  ├── frontend (172.18.0.3:80)       │
│  ├── database (172.18.0.4:5432)     │
│  └── redis (172.18.0.5:6379)        │
│                                     │
│  Host (192.168.1.100)               │
│  ├── :80 → frontend:80              │
│  ├── :8000 → backend:8000           │
│  └── :5432 → database:5432 (optional)
│                                     │
└─────────────────────────────────────┘
```

### Service Communication

**Frontend → Backend (internal):**
```nginx
# In nginx.conf (docker/default.conf)
upstream django_backend {
    server backend:8000;  # DNS name resolves in Docker network
}

location /api/ {
    proxy_pass http://django_backend;
}
```

**Backend → Database (internal):**
```python
# In Django settings
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'HOST': 'database',  # Docker DNS name
        'PORT': 5432,
        'USER': 'opd_user',
    }
}
```

### DNS Resolution

Docker's built-in DNS server:
- Service name resolves to container IP
- Port is always service's internal port (not host-mapped port)

```bash
# From frontend container
curl http://backend:8000/  # Works - service name + internal port

# From host machine
curl http://localhost:8000/  # Works - host-mapped port

# From database
curl http://backend:8000/  # Works - internal communication
curl http://192.168.1.100:8000/  # Also works - host IP
```

---

## 📦 Volume Management

### Volume Types

```yaml
services:
  backend:
    # Named volume - managed by Docker
    volumes:
      - backend_static:/app/staticfiles
      
    # Bind mount - direct host directory
    volumes:
      - ./backend:/app
      
    # Read-only mount
    volumes:
      - ./config:/app/config:ro
```

### Volume Purposes

| Volume | Purpose | Persistence | Read-Only |
|--------|---------|-------------|-----------|
| `postgres_data` | Database files | Yes (data persists) | No |
| `backend_static` | Collected static files | Yes | No |
| `backend_logs` | Application logs | Yes | No |
| `frontend_logs` | Nginx logs | Yes | No |
| `./backend` | Source code | Yes | Development |

### Backup & Restore Volumes

```bash
# Backup volume
docker run --rm \
  -v postgres_data:/data \
  -v $(pwd):/backup \
  alpine tar czf /backup/postgres_data.tar.gz /data

# Restore volume
docker run --rm \
  -v postgres_data:/data \
  -v $(pwd):/backup \
  alpine tar xzf /backup/postgres_data.tar.gz -C /

# Cleanup
docker volume prune  # Remove unused volumes
```

---

## ⚡ Performance Optimization

### Image Size Optimization

```dockerfile
# ❌ Before (1.2GB)
FROM python:3.11
RUN apt-get update && apt-get install -y \
    git curl wget gcc build-essential \
    postgresql-client mysql-client
COPY . /app
RUN pip install -r requirements.txt

# ✅ After (350MB)
FROM python:3.11-slim as builder
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential postgresql-client
RUN python -m venv /opt/venv && \
    pip install --no-cache-dir -r requirements.txt

FROM python:3.11-slim
COPY --from=builder /opt/venv /opt/venv
COPY --chown=django:django . .
USER django
```

### Build Layer Caching

```dockerfile
# ❌ Bad - rebuilds dependencies on code change
FROM python:3.11-slim
COPY . /app
RUN pip install -r requirements.txt

# ✅ Good - caches dependencies, only rebuilds on requirements change
FROM python:3.11-slim
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . /app
```

### Runtime Performance

```dockerfile
# Use slim/alpine images
FROM python:3.11-slim  # Good
FROM node:18-alpine    # Good

# Don't use latest tag (unpredictable)
FROM python:3.11-slim  # Good
FROM python:latest     # Bad

# Multi-worker for production
CMD ["gunicorn", "--workers", "3", "--worker-class", "sync"]

# Enable Keep-Alive
RUN echo "http_keepalive_timeout 65;" >> /etc/nginx/nginx.conf
```

---

## 🔍 Monitoring & Debugging

### View Running Containers

```bash
# List containers with status
docker-compose ps

# Show detailed info
docker inspect opd-backend

# Show running processes in container
docker top opd-backend

# Show port mappings
docker port opd-backend
```

### Access Container

```bash
# Execute command
docker exec opd-backend python manage.py migrate

# Interactive shell
docker exec -it opd-backend bash

# Python shell
docker exec -it opd-backend python manage.py shell
```

### View Logs

```bash
# Last 50 lines
docker logs --tail 50 opd-backend

# Follow logs (stream)
docker logs -f opd-backend

# Show timestamps
docker logs --timestamps opd-backend

# From specific time
docker logs --since 2026-04-29T10:00:00Z opd-backend
```

### Monitor Resources

```bash
# Show resource usage (live)
docker stats opd-backend opd-frontend

# Example output:
# CONTAINER    CPU %    MEM USAGE / LIMIT     MEM %
# opd-backend  0.05%    145MiB / 8GiB         1.81%
# opd-frontend 0.01%    12MiB / 8GiB          0.15%
```

### Inspect Network

```bash
# Show container network
docker network inspect opd_network

# Test DNS resolution
docker exec opd-backend nslookup database

# Test connectivity
docker exec opd-backend curl -v http://frontend/health
```

---

## 🚀 Production Checklist

Before deploying to production:

- [ ] **Images:** Built with correct versions, tested locally
- [ ] **Security:** Non-root users, no secrets in Dockerfile
- [ ] **Health Checks:** All services have health checks
- [ ] **Volumes:** Database and log volumes configured
- [ ] **Networks:** Services communicate correctly
- [ ] **Environment:** `.env` file created with production values
- [ ] **Migrations:** Database migrations will run on startup
- [ ] **Static Files:** Collected and served correctly
- [ ] **Logs:** Persisted to volumes, not to container stdout
- [ ] **Backups:** Database backup strategy in place
- [ ] **Monitoring:** Health checks, metrics collection configured
- [ ] **Security Headers:** HTTP security headers configured
- [ ] **SSL/TLS:** HTTPS certificates ready (if using)
- [ ] **Firewall:** Only necessary ports exposed
- [ ] **Documentation:** Updated deployment instructions

---

## 📞 Quick Reference

```bash
# Build
docker-compose build

# Start
docker-compose up -d

# View status
docker-compose ps

# View logs
docker-compose logs -f backend

# Stop
docker-compose down

# Database operations
docker-compose exec backend python manage.py migrate
docker-compose exec backend python manage.py createsuperuser

# Backup
docker-compose exec -T database pg_dump -U opd_user opd_management > backup.sql

# Cleanup
docker system prune -a
```

---

**Document Version:** 1.0.0  
**Last Updated:** April 29, 2026  
**Status:** Production Ready
