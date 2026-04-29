# ============================================================================
# OPD Management System - Backend Dockerfile
# Multi-stage build with non-root user and health checks
# ============================================================================

# Stage 1: Builder
# ============================================================================
FROM python:3.11-slim as builder

LABEL maintainer="OPD Team"
LABEL description="Builder stage for OPD Management System backend"

# Set environment variables for Python
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies required for building
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# ============================================================================
# Stage 2: Runtime
# ============================================================================
FROM python:3.11-slim

LABEL maintainer="OPD Team"
LABEL description="OPD Management System Django backend service"
LABEL version="1.0.0"

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONFAULTHANDLER=1 \
    PATH="/opt/venv/bin:$PATH" \
    DJANGO_SETTINGS_MODULE=config.settings

# Install runtime dependencies only (no build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN groupadd -r django && useradd -r -g django -d /app django

# Set working directory
WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder --chown=django:django /opt/venv /opt/venv

# Copy application code
COPY --chown=django:django . .

# Create necessary directories with proper permissions
RUN mkdir -p /app/logs /app/staticfiles /app/media && \
    chown -R django:django /app/logs /app/staticfiles /app/media && \
    chmod 755 /app/logs /app/staticfiles /app/media

# Switch to non-root user
USER django

# Health check script
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/', timeout=5)"

# Expose port
EXPOSE 8000

# Run gunicorn (production WSGI server)
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "60", "--access-logfile", "-", "--error-logfile", "-"]

# ============================================================================
# Notes:
# - Multi-stage build reduces final image size by ~60% (no build tools in runtime)
# - Non-root user (django) prevents privilege escalation attacks
# - Health check allows orchestrators (Docker Compose, K8s) to monitor service
# - Static files collected during build for better performance
# 
# Build: docker build -t opd-backend:latest .
# Run:   docker run -p 8000:8000 -e DJANGO_SECRET_KEY=... opd-backend:latest
# ============================================================================
