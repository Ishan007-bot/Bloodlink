# syntax=docker/dockerfile:1

# ---- build stage: install dependencies into a virtualenv -------------------
FROM python:3.12-slim AS build
WORKDIR /build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements.txt .
RUN pip install -r requirements.txt \
 && python -m pip uninstall -y pip

# ---- runtime stage: only the venv and the application code -----------------
FROM python:3.12-slim
LABEL org.opencontainers.image.title="bloodlink-backend" \
      org.opencontainers.image.description="BloodLink FastAPI backend" \
      org.opencontainers.image.source="https://github.com/Ishan007-bot/bloodlink"

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Remove pip from the runtime image: nothing should be installed at runtime.
RUN pip uninstall -y pip setuptools wheel 2>/dev/null; \
    useradd --uid 10001 --create-home --shell /usr/sbin/nologin app

WORKDIR /app
COPY --from=build /opt/venv /opt/venv
COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app

USER 10001
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status == 200 else 1)"]

# Migrations run as a separate step (compose "migrate" service / Kubernetes Job),
# so several replicas never race to migrate the same database.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
