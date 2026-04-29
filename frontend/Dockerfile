# ============================================================================
# OPD Management System - Frontend Dockerfile
# Nginx-based static/template server with multi-stage build
# ============================================================================

# Stage 1: Assets
# ============================================================================
FROM alpine:3.20 as assets

LABEL maintainer="OPD Team"
LABEL description="Assets stage for OPD Management System frontend"

WORKDIR /app

# Copy only static frontend assets
COPY frontend/static ./frontend/static
COPY frontend/templates ./frontend/templates

# ============================================================================
# Stage 2: Runtime
# ============================================================================
FROM nginxinc/nginx-unprivileged:1.27-alpine

LABEL maintainer="OPD Team"
LABEL description="OPD Management System frontend (Nginx)"
LABEL version="1.0.0"

# Install wget for health checks
RUN apk add --no-cache wget

# Remove default nginx config
RUN rm -f /etc/nginx/conf.d/default.conf

# Copy custom nginx configuration
COPY docker/nginx.conf /etc/nginx/nginx.conf
COPY docker/default.conf /etc/nginx/conf.d/default.conf

# Copy frontend assets from builder
COPY --from=assets /app/frontend/static /usr/share/nginx/html/static
COPY --from=assets /app/frontend/templates /usr/share/nginx/html/templates

# Create cache and log directories with proper permissions
RUN mkdir -p /var/cache/nginx /var/log/nginx /tmp/nginx && \
    chown -R nginx:nginx /var/cache/nginx /var/log/nginx /usr/share/nginx/html /tmp/nginx

# Verify nginx configuration
RUN nginx -t

# Health check - verifies nginx is responding
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1:8080/health || exit 1

# Expose port
EXPOSE 8080

# Run nginx in foreground
CMD ["nginx", "-g", "daemon off;"]

# ============================================================================
# Notes:
# - Uses official nginx:alpine for minimal image size (~50MB vs 300MB+)
# - Non-root user (nginx) prevents privilege escalation
# - Multi-stage build reduces final image size
# - Health check monitors service availability
# - Static files and templates served efficiently by Nginx
# 
# Build: docker build -t opd-frontend:latest .
# Run:   docker run -p 80:80 opd-frontend:latest
# ============================================================================
