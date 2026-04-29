# Docker Deployment Guide - OPD Management System

**Version:** 1.0.0  
**Created:** April 29, 2026  
**Status:** Production-Ready

---

## 📋 Table of Contents

1. [Quick Start](#quick-start)
2. [Architecture Overview](#architecture-overview)
3. [Prerequisites](#prerequisites)
4. [Configuration](#configuration)
5. [Building Images](#building-images)
6. [Running Services](#running-services)
7. [Monitoring & Logs](#monitoring--logs)
8. [Troubleshooting](#troubleshooting)
9. [Security](#security)
10. [Production Deployment](#production-deployment)

---

## 🚀 Quick Start

### Start all services (development):
```bash
# Copy environment template
cp .env.example .env

# Start Docker Compose
docker-compose up -d

# Run migrations
docker-compose exec backend python manage.py migrate

# Create superuser
docker-compose exec backend python manage.py createsuperuser

# Access application:
# Frontend: http://localhost
# API: http://localhost:8000/api/
# Admin: http://localhost:8000/admin/
```

### Stop all services:
```bash
docker-compose down

# Include removing volumes (WARNING: deletes data):
docker-compose down -v
```

---

## 🏗️ Architecture Overview

### Multi-Container Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Docker Network (opd_network)              │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────┐      ┌──────────────┐   ┌─────────────┐  │
│  │   Frontend   │      │   Backend    │   │  Database   │  │
│  │   (Nginx)    │◄────►│  (Django/    │◄─►│(PostgreSQL) │  │
│  │   Port 80    │      │  Gunicorn)   │   │  Port 5432  │  │
│  │              │      │  Port 8000   │   │             │  │
│  └──────────────┘      └──────────────┘   └─────────────┘  │
│         ▲                      ▲                   ▲          │
│         │                      │                   │          │
│      static/                proxy/              Django       │
│      templates               api                 ORM          │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │               Optional: Redis Cache                  │   │
│  │                  (Port 6379)                         │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

---

## ✅ Prerequisites

### System Requirements
- **Docker:** 20.10+
- **Docker Compose:** 1.29+
- **Disk Space:** 5GB+ for images and volumes
- **RAM:** 4GB minimum (8GB recommended)
- **CPU:** 2 cores minimum

### Installation

**macOS:**
```bash
# Install Docker Desktop (includes Docker and Docker Compose)
brew install --cask docker

# Start Docker
open /Applications/Docker.app
```

**Linux (Ubuntu/Debian):**
```bash
# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Add user to docker group
sudo usermod -aG docker $USER
newgrp docker
```

**Windows:**
```powershell
# Install Docker Desktop for Windows
# Download from https://www.docker.com/products/docker-desktop
```

### Verify Installation
```bash
docker --version
docker-compose --version
docker run hello-world
```

---

## ⚙️ Configuration

### 1. Environment Setup

```bash
# Copy example environment file
cp .env.example .env

# Edit with your settings
nano .env
```

### 2. Required Environment Variables

**Critical (must change for production):**
- `DJANGO_SECRET_KEY` - Generate: `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`
- `DB_PASSWORD` - Strong database password
- `ALLOWED_HOSTS` - Your domain/IPs

**Database:**
```env
DB_ENGINE=postgresql
DB_NAME=opd_management
DB_USER=opd_user
DB_PASSWORD=your-secure-password
DB_HOST=database
DB_PORT=5432
```

**Security:**
```env
DEBUG=False
SECURE_SSL_REDIRECT=True
SECURE_HSTS_SECONDS=31536000
```

### 3. Health Check Configuration

Each service has health checks configured:

```yaml
# Backend health check
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8000/health/"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 40s

# Frontend health check
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost/health"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 40s
```

View health status:
```bash
docker-compose ps  # Shows health status (starting, healthy, unhealthy)
```

---

## 🔨 Building Images

### Build All Images

```bash
# Build with Docker Compose
docker-compose build

# Build specific service
docker-compose build backend
docker-compose build frontend

# Build without cache (fresh build)
docker-compose build --no-cache
```

### Build Individual Dockerfiles

```bash
# Backend image
cd backend
docker build -t opd-backend:latest .
docker build -t opd-backend:1.0.0 .

# Frontend image
cd frontend
docker build -t opd-frontend:latest .
docker build -t opd-frontend:1.0.0 .
```

### View Built Images
```bash
docker images | grep opd
```

### Push to Registry

```bash
# Tag image
docker tag opd-backend:latest myregistry.azurecr.io/opd-backend:latest

# Login to registry
docker login myregistry.azurecr.io

# Push image
docker push myregistry.azurecr.io/opd-backend:latest
```

---

## 🎬 Running Services

### Start Services

```bash
# Start all services in background
docker-compose up -d

# Start with logs visible
docker-compose up

# Start specific service
docker-compose up -d backend
docker-compose up -d frontend
```

### Stop Services

```bash
# Stop all services
docker-compose stop

# Stop specific service
docker-compose stop backend

# Stop and remove containers
docker-compose down

# Stop and remove everything (including volumes)
docker-compose down -v
```

### Restart Services

```bash
# Restart all services
docker-compose restart

# Restart specific service
docker-compose restart backend
```

---

## 🔧 Database Management

### Run Migrations

```bash
# Apply migrations
docker-compose exec backend python manage.py migrate

# Make migrations
docker-compose exec backend python manage.py makemigrations

# Show migration status
docker-compose exec backend python manage.py showmigrations
```

### Create Superuser

```bash
docker-compose exec backend python manage.py createsuperuser
```

### Database Access

```bash
# Connect to PostgreSQL
docker-compose exec database psql -U opd_user -d opd_management

# Or use database client
psql -h localhost -U opd_user -d opd_management
```

### Backup Database

```bash
# Backup to file
docker-compose exec database pg_dump -U opd_user opd_management > backup.sql

# Restore from file
docker-compose exec -T database psql -U opd_user opd_management < backup.sql
```

---

## 📊 Monitoring & Logs

### View Logs

```bash
# All services
docker-compose logs

# Specific service
docker-compose logs backend
docker-compose logs frontend
docker-compose logs database

# Follow logs in real-time
docker-compose logs -f backend

# Last 100 lines
docker-compose logs --tail=100 backend

# Show timestamps
docker-compose logs --timestamps backend
```

### Container Status

```bash
# Show running containers and health status
docker-compose ps

# Show detailed container info
docker inspect opd-backend

# Show resource usage
docker stats opd-backend opd-frontend opd-db
```

### Access Container Shell

```bash
# Backend shell
docker-compose exec backend bash
docker-compose exec backend python manage.py shell

# Frontend shell
docker-compose exec frontend sh

# Database shell
docker-compose exec database psql -U opd_user -d opd_management
```

---

## 🐛 Troubleshooting

### Service Won't Start

```bash
# Check logs
docker-compose logs backend

# Common issues:
# 1. Port already in use - change port in docker-compose.yml
# 2. Out of disk space - docker system prune
# 3. Database not ready - wait for healthy status (docker-compose ps)
```

### Database Connection Error

```bash
# Check database is running
docker-compose ps database

# Check database logs
docker-compose logs database

# Test connection from backend
docker-compose exec backend python manage.py dbshell

# Reset database (WARNING: deletes data)
docker-compose down -v
docker-compose up -d
```

### Frontend Not Loading

```bash
# Check nginx logs
docker-compose logs frontend

# Check nginx configuration
docker-compose exec frontend nginx -t

# Check if backend is accessible
docker-compose exec frontend curl http://backend:8000/

# Rebuild frontend
docker-compose rebuild frontend
```

### Health Check Failing

```bash
# Check individual health checks
docker-compose exec backend curl http://localhost:8000/health/
docker-compose exec frontend curl http://localhost/health

# View health check logs
docker inspect --format='{{json .State.Health}}' opd-backend | jq

# Wait for service to be healthy
docker-compose exec backend sleep 30
```

### Out of Disk Space

```bash
# Remove unused images
docker image prune -a

# Remove unused volumes
docker volume prune

# Remove unused containers
docker container prune

# Full cleanup (removes stopped containers, dangling images, unused networks)
docker system prune -a
```

---

## 🔒 Security

### Non-Root Users

All containers run as non-root users:
- **Backend:** `django` user
- **Frontend:** `nginx` user
- **Database:** `postgres` user

### Security Headers

Frontend (Nginx) includes security headers:
```
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
X-XSS-Protection: 1; mode=block
Referrer-Policy: strict-origin-when-cross-origin
```

### HTTPS/TLS

For production, configure HTTPS:

```yaml
# In docker-compose.yml
frontend:
  ports:
    - "80:80"
    - "443:443"
  volumes:
    - ./docker/ssl:/etc/nginx/ssl:ro  # Mount SSL certificates
```

Configure in `docker/default.conf`:
```nginx
server {
    listen 443 ssl http2;
    ssl_certificate /etc/nginx/ssl/opd.crt;
    ssl_certificate_key /etc/nginx/ssl/opd.key;
    # ... rest of config
}
```

### Environment Variables Security

Never commit `.env` to git:
```bash
echo ".env" >> .gitignore
```

For production, use:
- **Kubernetes Secrets:** for K8s deployments
- **AWS Secrets Manager:** for AWS
- **HashiCorp Vault:** for enterprise setups

### Network Isolation

Services communicate only through Docker network:
- Frontend → Backend (internal, no external API calls needed)
- Backend → Database (isolated, not exposed)
- Redis → Backend (isolated)

---

## 🚀 Production Deployment

### Pre-Deployment Checklist

- [ ] `DEBUG=False` in `.env`
- [ ] Generated strong `DJANGO_SECRET_KEY`
- [ ] Set secure `DB_PASSWORD`
- [ ] Configured `ALLOWED_HOSTS`
- [ ] Set `SECURE_SSL_REDIRECT=True`
- [ ] Configured email settings
- [ ] Set up HTTPS/TLS certificates
- [ ] Created admin superuser
- [ ] Ran all migrations
- [ ] Collected static files
- [ ] Tested health checks pass
- [ ] Configured backups
- [ ] Set up monitoring/logging

### Deployment Options

#### Option 1: Docker Compose on Single Server

```bash
# SSH into server
ssh user@clinic-server

# Clone repository
git clone <repo-url>
cd OPD_MANAGEMENT_SYSTEM

# Copy environment file
cp .env.example .env
nano .env  # Edit with production settings

# Start services
docker-compose up -d

# Verify health
docker-compose ps
```

#### Option 2: Kubernetes (EKS, AKS, GKE)

See `kubernetes/` directory for K8s manifests.

```bash
kubectl apply -f kubernetes/backend-deployment.yml
kubectl apply -f kubernetes/frontend-deployment.yml
kubectl apply -f kubernetes/database-statefulset.yml
```

#### Option 3: Docker Swarm

```bash
# Initialize swarm
docker swarm init

# Deploy stack
docker stack deploy -c docker-compose.yml opd_system
```

### Monitoring & Alerting

**Recommended Tools:**
- **Prometheus:** Metrics collection
- **Grafana:** Metrics visualization
- **ELK Stack:** Centralized logging
- **Sentry:** Error tracking
- **DataDog:** APM and monitoring

### Backup Strategy

```bash
# Daily database backups
0 2 * * * docker-compose -f /path/to/docker-compose.yml exec -T database pg_dump -U opd_user opd_management > /backups/opd_$(date +\%Y\%m\%d).sql

# Store backups to S3/Cloud
aws s3 cp /backups/opd_*.sql s3://opd-backups/
```

### Scaling

**Horizontal Scaling (Load Balancing):**
```yaml
backend:
  deploy:
    replicas: 3  # Run 3 backend instances
```

Use HAProxy or Nginx as load balancer:
```nginx
upstream backend {
    server backend-1:8000;
    server backend-2:8000;
    server backend-3:8000;
}
```

---

## 📞 Support

For issues or questions:

1. Check logs: `docker-compose logs -f service-name`
2. Review troubleshooting section above
3. Check health: `docker-compose ps`
4. Consult Dockerfiles for configuration details

---

## 📚 Additional Resources

- [Docker Documentation](https://docs.docker.com/)
- [Docker Compose Reference](https://docs.docker.com/compose/compose-file/)
- [Django Deployment Guide](https://docs.djangoproject.com/en/4.2/howto/deployment/)
- [Nginx Documentation](https://nginx.org/en/docs/)
- [PostgreSQL Docker Hub](https://hub.docker.com/_/postgres)

---

**Last Updated:** April 29, 2026  
**Status:** Production Ready
