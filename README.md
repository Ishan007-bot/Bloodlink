# BloodLink

**Blood bank inventory and hospital request system.** Donors give blood, every unit is tracked
until it is used or expires, and hospitals request units for patients. BloodLink allocates
**compatible** blood, uses the **oldest units first** so less blood is wasted, serves
**emergencies first**, and warns before stock of any blood group runs out.

[![CI/CD](https://github.com/Ishan007-bot/Bloodlink/actions/workflows/ci-cd.yml/badge.svg)](https://github.com/Ishan007-bot/Bloodlink/actions/workflows/ci-cd.yml)

> DevOps final capstone. Evidence for every rubric module, with screenshots: **[docs/EVIDENCE.md](docs/EVIDENCE.md)**. Demo recording (commit → pipeline → deployment): **[docs/demo/bloodlink-demo.mp4](docs/demo/bloodlink-demo.mp4)**.

---

## What it does

| Feature | Rule |
| :--- | :--- |
| Donor registry | 8 blood groups; a donor may give whole blood again only **90 days** after the last donation (`409 Conflict` otherwise) |
| Blood units | Each donation becomes one unit that **expires 42 days** after collection; expired units are never issued |
| Hospital requests | Routine or emergency, 1–20 units; can be partially filled, completed or cancelled |
| Compatible allocation | ABO/Rh red-cell compatibility. Exact group first, then compatible substitutes, **O- (universal donor) always last** so it is kept for patients who can receive nothing else |
| First-expiring-first-out | Within a group, the unit closest to expiry is used first |
| Emergency queue | "Process queue" fills open requests emergencies-first, then oldest-first |
| Stock levels | Per group: OK / LOW (below safety stock of 10) / CRITICAL (below 5), plus units expiring within 7 days |
| Reporting | Fill rate, wastage rate, average emergency fill time, live Prometheus metrics |

### Compatibility (who can receive from whom)

| Recipient | Can receive (in allocation order) |
| :--- | :--- |
| O- | O- |
| O+ | O+, O- |
| A- | A-, O- |
| A+ | A+, A-, O+, O- |
| B- | B-, O- |
| B+ | B+, B-, O+, O- |
| AB- | AB-, A-, B-, O- |
| AB+ | AB+, AB-, A+, A-, B+, B-, O+, O- |

---

## Architecture

```mermaid
flowchart LR
    user([Browser]) --> ing[Ingress<br/>ingress-nginx]
    subgraph k8s["Kubernetes namespace bloodlink (Pod Security: restricted)"]
        ing -- "/" --> fe[frontend<br/>React + Nginx<br/>2 replicas]
        ing -- "/api" --> be[backend<br/>FastAPI<br/>HPA 2-6]
        fe -- "/api proxy" --> be
        be --> db[(PostgreSQL 16<br/>StatefulSet + PVC)]
        bk[backup CronJob<br/>pg_dump nightly] --> db
    end
    prom[Prometheus] -- "scrapes /metrics" --> be
    graf[Grafana<br/>provisioned dashboard] --> prom
    am[Alertmanager] --- prom

    dev([git push]) --> gha[GitHub Actions]
    gha -- "test, lint, scan" --> gha
    gha -- "SHA-tagged images" --> ghcr[(GHCR)]
    gha -- "helm upgrade (OIDC)" --> k8s
    ghcr -. pull .-> k8s
    tf[Terraform] --> aws["AWS: VPC + EKS<br/>NAT, EBS CSI, metrics-server"]
```

| Layer | Technology |
| :--- | :--- |
| Frontend | React 19 + Vite, served by unprivileged Nginx (non-root, read-only filesystem) |
| Backend | Python 3.12, FastAPI, SQLAlchemy 2, Alembic, Pydantic v2 |
| Database | PostgreSQL 16 |
| Tests | pytest (81 tests, 97 % coverage), ruff lint + format |
| Containers | Multi-stage Docker builds on Alpine, non-root users, read-only root filesystem, Docker Compose |
| CI/CD | GitHub Actions: tests → frontend build → secret & dependency scan → IaC checks → image build → Trivy gate → GHCR → Helm deploy |
| Security | Trivy (images + IaC; fails on any HIGH/CRITICAL, fixed or not), gitleaks, pip-audit, npm audit, Pod Security "restricted", NetworkPolicy, OIDC (no AWS keys in GitHub) |
| Infrastructure | Terraform: VPC (2 public + 2 private subnets, NAT), EKS with managed node group and add-ons, S3 remote state |
| Kubernetes | Helm chart: Deployments, StatefulSet, Services, Ingress, HPA, PDB, NetworkPolicy, CronJob, Secret |
| Observability | kube-prometheus-stack: ServiceMonitor, 7 alert rules, Grafana dashboard provisioned from the chart |

---

## Repository layout

```text
backend/            FastAPI app (app/), Alembic migrations, tests/, Dockerfile
frontend/           React app (src/), Nginx config template, Dockerfile
docker-compose.yml  postgres -> migrate -> backend -> frontend (+ optional seed)
.github/workflows/  CI/CD pipeline
terraform/          AWS VPC + EKS (+ bootstrap/ for the S3 state bucket)
helm/bloodlink/     Helm chart (values.yaml, values-kind.yaml, values-eks.yaml)
k8s/                namespace, kind cluster config, gp3 StorageClass
monitoring/         kube-prometheus-stack values (Prometheus + Grafana)
troubleshooting/    deliberately broken manifests for the troubleshooting lab
scripts/            kind-up.ps1 / eks-up.ps1 platform setup
docs/               EVIDENCE.md (rubric screenshots), RUNBOOK.md, DEPLOYMENT.md
```

---

## Run it

### 1. Docker Compose (quickest)

```powershell
docker compose up --build                  # http://localhost:3000
docker compose --profile demo up --build   # same, plus realistic demo data
```

Compose starts PostgreSQL, waits for it to be healthy, runs the migrations once, starts the
backend once migrations succeed, then the frontend once the backend is healthy.
API docs: http://localhost:8000/docs. Stop with `docker compose down` (add `-v` to delete the data).

### 2. Backend directly

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
$env:DATABASE_URL = "postgresql+psycopg://bloodlink:bloodlink@localhost:5433/bloodlink"
.\.venv\Scripts\alembic upgrade head
.\.venv\Scripts\uvicorn app.main:app --reload --port 8000
```

### 3. Tests and lint

```powershell
cd backend
.\.venv\Scripts\ruff check . ; .\.venv\Scripts\ruff format --check .
.\.venv\Scripts\pytest -v --cov=app
```

Tests use a throwaway SQLite database configured in `tests/conftest.py`, never PostgreSQL.

### 4. Kubernetes on your laptop (kind)

```powershell
./scripts/kind-up.ps1 -Tag <git-sha>    # cluster, ingress-nginx, metrics-server, Prometheus/Grafana, BloodLink
```

Then open http://bloodlink.localhost. Details: [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

### 5. AWS (Terraform + EKS)

```powershell
terraform -chdir=terraform/bootstrap init; terraform -chdir=terraform/bootstrap apply   # state bucket
terraform -chdir=terraform init -backend-config=backend.hcl
terraform -chdir=terraform apply
./scripts/eks-up.ps1 -Tag <git-sha>
terraform -chdir=terraform destroy      # when finished: EKS and NAT are billed per hour
```

---

## API

Swagger UI at `/docs`.

| Method | Route | Purpose |
| :--- | :--- | :--- |
| GET | `/health` | Liveness (does not touch the database) |
| GET | `/ready` | Readiness (checks the database) |
| GET | `/metrics` | Prometheus metrics |
| GET, POST | `/api/donors` | List (filter by group / eligibility), register |
| GET, PUT, DELETE | `/api/donors/{id}` | Read, update, remove a donor |
| POST | `/api/donations` | Record a donation → new unit (90-day rule) |
| GET | `/api/units` | Units, filter by status / group |
| GET, POST | `/api/hospitals` | List, add |
| GET, PUT, DELETE | `/api/hospitals/{id}` | Read, update, remove |
| GET, POST | `/api/requests` | List (filter by status / priority), raise a request |
| GET, PUT, DELETE | `/api/requests/{id}` | Read, change or cancel, delete |
| POST | `/api/requests/{id}/fulfil` | Allocate compatible units |
| POST | `/api/requests/process-queue` | Fill all open requests, emergencies first |
| GET | `/api/inventory` | Stock and expiring units per blood group |
| GET | `/api/stats` | Fill rate, wastage, emergency fill time |
| GET | `/api/compatibility` | The compatibility table |

---

## Operations

- **Troubleshooting:** [docs/RUNBOOK.md](docs/RUNBOOK.md): image pull failures, empty Services,
  database outages, bad secrets, OOM kills, rollbacks, alerts, backups.
- **Monitoring:** Grafana dashboard "BloodLink - Blood Bank Overview" (stock, expiry, fulfilment
  time, request rate, errors, latency, CPU, HPA replicas) and 7 Prometheus alert rules.
- **Security:** no credentials in Git (gitleaks runs on the full history in CI); database
  credentials live in a Kubernetes Secret; GitHub deploys to AWS with short-lived OIDC credentials.
