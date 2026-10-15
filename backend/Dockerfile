# syntax=docker/dockerfile:1

# Alpine, not Debian slim: slim carries ~44 HIGH CVEs with no fix yet (util-linux, ncurses,
# systemd, perl) in packages this app never runs, and the Trivy gate fails on unfixed CVEs too.
# Every dependency ships musllinux wheels, so nothing is compiled.

# ---- build stage: install dependencies into a virtualenv -------------------
FROM python:3.12-alpine AS build
WORKDIR /build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements.txt .
RUN pip install -r requirements.txt \
 && python -m pip uninstall -y pip

# ---- runtime stage: only the venv and the application code -----------------
FROM python:3.12-alpine
LABEL org.opencontainers.image.title="bloodlink-backend" \
      org.opencontainers.image.description="BloodLink FastAPI backend" \
      org.opencontainers.image.source="https://github.com/Ishan007-bot/Bloodlink"

# The commit this image was built from (set by CI), reported by GET /.
ARG GIT_SHA=dev
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    GIT_SHA=$GIT_SHA

# Pull in Alpine security fixes published after the base image, then remove pip and the wheels
# ensurepip bundles (Trivy scans the packages vendored inside pip): nothing installs at runtime.
RUN apk upgrade --no-cache \
 && { pip uninstall -y pip setuptools wheel 2>/dev/null || true; } \
 && rm -rf /usr/local/lib/python3.12/ensurepip \
 && adduser -D -u 10001 -h /home/app -s /sbin/nologin app

WORKDIR /app
COPY --from=build /opt/venv /opt/venv
COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app

USER 10001
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status == 200 else 1)"]

# Migrations run before the server starts, outside this CMD: the compose "migrate" service, or the
# "migrate" init container of each Kubernetes pod. alembic/env.py holds a PostgreSQL advisory lock,
# so replicas starting together never migrate the same database at the same time.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
