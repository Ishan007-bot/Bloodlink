# BloodLink: evidence

Screenshots for every module of the grading rubric, in rubric order. Every screenshot was taken
from the real system: the application on a local Kubernetes cluster (kind) and Docker Compose,
the GitHub Actions pipeline of this repository, and GHCR.

- Repository: https://github.com/Ishan007-bot/Bloodlink
- Pipeline: https://github.com/Ishan007-bot/Bloodlink/actions
- Images: `ghcr.io/ishan007-bot/bloodlink-backend` and `ghcr.io/ishan007-bot/bloodlink-frontend`, tagged with the commit SHA

| Module | Section |
| :--- | :--- |
| M1 Application | [Application](#m1-application) |
| M2 Testing | [Testing](#m2-testing) |
| M3 Git and GitHub | [Git](#m3-git-and-github) |
| M4 Docker | [Docker](#m4-docker) |
| M5 CI/CD | [CI/CD](#m5-cicd) |
| M6 DevSecOps | [Security](#m6-devsecops) |
| M7 Terraform | [Terraform](#m7-terraform) |
| M8 Kubernetes + Helm | [Kubernetes](#m8-kubernetes--helm) |
| M9 Observability | [Observability](#m9-observability) |
| M10 Live demo | [Commit to deployment](#m10-live-demo-commit--pipeline--deployment) |
| Troubleshooting | [Troubleshooting lab](#troubleshooting-lab) |

---

## M1 Application

FastAPI backend, React frontend, PostgreSQL 16 with Alembic migrations.

| Criterion | Evidence |
| :--- | :--- |
| Backend responds to `/health` | [08-api-crud](evidence/01-application/08-api-crud.png), [03-non-root-read-only](evidence/04-docker/03-non-root-read-only.png) |
| GET, POST, PUT, DELETE endpoints | [08-api-crud](evidence/01-application/08-api-crud.png): a donor is created, read, updated and deleted (204). Full list in [Swagger](evidence/01-application/07-swagger.png) |
| PostgreSQL tables managed by Alembic | [09-database-tables](evidence/01-application/09-database-tables.png): 5 tables plus `alembic_version` = `0001_initial_schema` |
| Frontend renders and calls the API | [01-dashboard](evidence/01-application/01-dashboard.png), [02-requests](evidence/01-application/02-requests.png), [04-donors](evidence/01-application/04-donors.png), [05-hospitals](evidence/01-application/05-hospitals.png) |
| Responsive, usable UI | [06-mobile](evidence/01-application/06-mobile.png) (390 px wide phone) |

The core rule of the domain, compatible allocation that uses the units closest to expiry first:
[03-fulfil-result](evidence/01-application/03-fulfil-result.png). A B+ request is filled with
three B+ units that expire in 4, 4 and 5 days, so blood that would soon be wasted is used first.

![Dashboard](evidence/01-application/01-dashboard.png)

## M2 Testing

| Criterion | Evidence |
| :--- | :--- |
| `pytest` runs without errors | [01-pytest-verbose](evidence/02-testing/01-pytest-verbose.png): **81 passed** |
| At least 5 tests over 3 or more endpoints | 81 tests over every endpoint group: compatibility rules, allocation, donors, donations, hospitals, requests, fulfilment, queue, inventory, stats, health, metrics, migrations |
| Test database, not production | `tests/conftest.py` sets `DATABASE_URL=sqlite:///./test.db` before the app is imported ([02-coverage-and-lint](evidence/02-testing/02-coverage-and-lint.png)) |
| `pytest.ini` / `conftest.py` | Both present, shown in [02-coverage-and-lint](evidence/02-testing/02-coverage-and-lint.png) |

Also: **97 % line coverage**, `ruff check` and `ruff format --check` clean. CI fails if coverage
drops below 90 %.

## M3 Git and GitHub

| Criterion | Evidence |
| :--- | :--- |
| Public repository | [03-github-repo](evidence/03-git/03-github-repo.png) |
| Meaningful commit messages, 10+ commits | [01-commit-history](evidence/03-git/01-commit-history.png), [04-github-commits](evidence/03-git/04-github-commits.png) |
| `.gitignore` excludes `.env`, `__pycache__`, `node_modules`, `.venv` | [02-gitignore](evidence/03-git/02-gitignore.png): `git check-ignore` confirms each path is ignored, plus Terraform state and `*.tfvars` |

Changes go through pull requests, and a pull request with a failing test cannot ship: see
[M5](#a-broken-change-is-stopped-by-the-pipeline).

## M4 Docker

| Criterion | Evidence |
| :--- | :--- |
| `backend/Dockerfile` builds | [01-compose-up-build](evidence/04-docker/01-compose-up-build.png): `bloodlink-backend:local Built` |
| Frontend multi-stage (Node build, Nginx runtime) | [03-non-root-read-only](evidence/04-docker/03-non-root-read-only.png): `FROM node:22-alpine AS build` then `FROM nginxinc/nginx-unprivileged` |
| Images run as non-root | [03-non-root-read-only](evidence/04-docker/03-non-root-read-only.png): backend `uid=10001(app)`, frontend `uid=101(nginx)`, both with a read-only root filesystem |
| `docker compose up --build` starts all services | [01-compose-up-build](evidence/04-docker/01-compose-up-build.png), [02-compose-ps](evidence/04-docker/02-compose-ps.png): postgres healthy, migrations exit 0, backend healthy, frontend started |
| Browser at `http://localhost:3000` | [04-browser-localhost-3000](evidence/04-docker/04-browser-localhost-3000.png) |

Start-up order is enforced with health checks: PostgreSQL healthy → `migrate` (Alembic) completes →
backend healthy → frontend. Migrations run once, not in every replica.

## M5 CI/CD

Workflow: [.github/workflows/ci-cd.yml](../.github/workflows/ci-cd.yml).

```text
push / pull request
  ├─ Backend lint and tests (ruff, pytest, coverage ≥ 90 %)
  ├─ Frontend build (npm ci, vite build)
  ├─ Secrets and dependency scan (gitleaks, pip-audit, npm audit)
  └─ Terraform, Helm and IaC scan (fmt, validate, helm lint, kubeconform, trivy config)
        └─ Build, scan and push images (docker build → Trivy gate → push to GHCR, tag = commit SHA)
              └─ Deploy to EKS (OIDC, helm upgrade --set image.tag=<sha>), main only
```

| Criterion | Evidence |
| :--- | :--- |
| Workflow file present | [03-workflow-triggers](evidence/05-cicd/03-workflow-triggers.png) |
| Triggers on push to `main` | [03-workflow-triggers](evidence/05-cicd/03-workflow-triggers.png), [01-actions-runs](evidence/05-cicd/01-actions-runs.png) |
| pytest in the pipeline fails the build | [The pull request below](#a-broken-change-is-stopped-by-the-pipeline) |
| Frontend built in the pipeline | [02-main-run-green](evidence/05-cicd/02-main-run-green.png) (job "Frontend build") |
| Images built for frontend and backend | [04-images-pushed](evidence/05-cicd/04-images-pushed.png) |
| Pushed to GHCR | [05-ghcr-backend](evidence/05-cicd/05-ghcr-backend.png), [11-ghcr-frontend](evidence/05-cicd/11-ghcr-frontend.png), [12-ghcr-packages](evidence/05-cicd/12-ghcr-packages.png) |
| Tags are the commit SHA, never `latest` | [04-images-pushed](evidence/05-cicd/04-images-pushed.png): the digest the pipeline pushed equals the digest GHCR serves for tag `e6491bf…` |

Green pipeline run: https://github.com/Ishan007-bot/Bloodlink/actions/runs/38637977804

### A broken change is stopped by the pipeline

[Pull request #1](https://github.com/Ishan007-bot/Bloodlink/pull/1) "Use O+ stock for A- patients"
looks helpful (A- stock is often low) but would give Rh-positive blood to Rh-negative patients.

1. [06-pr-tests-failing](evidence/05-cicd/06-pr-tests-failing.png): the PR is marked failing.
2. [07-pr-failing-log](evidence/05-cicd/07-pr-failing-log.png): `test_compatibility_pairs[O+-A--False]` fails: `is_compatible('O+', 'A-')` returned True.
3. [08-pr-run-blocked](evidence/05-cicd/08-pr-run-blocked.png): because tests failed, **no image was built and nothing was deployed**.
4. [09-pr-fixed-green](evidence/05-cicd/09-pr-fixed-green.png): the fix is pushed and every job passes.
5. [10-pr-merge](evidence/05-cicd/10-pr-merge.png): merged.

## M6 DevSecOps

| Criterion | Evidence |
| :--- | :--- |
| Trivy scans both images in CI | [01-trivy-ci-scan](evidence/06-security/01-trivy-ci-scan.png) |
| Fails on HIGH or CRITICAL | [02-trivy-gate-config](evidence/06-security/02-trivy-gate-config.png): `TRIVY_SEVERITY: HIGH,CRITICAL`, `trivy image --severity "$TRIVY_SEVERITY" --ignore-unfixed --exit-code 1`, before the push step |
| No secrets in Git | [03-secret-and-dependency-scan](evidence/06-security/03-secret-and-dependency-scan.png): gitleaks scanned all commits, `no leaks found` |

**What Trivy scanned and what the result means.** Trivy scanned both images built by the pipeline
(the Debian packages of `python:3.12-slim`, the Alpine packages of the Nginx image, and every
Python package in the backend's virtualenv) for known CVEs. The gate is set to fail the pipeline on
any HIGH or CRITICAL vulnerability that has a fix available. The result is 0 for both images,
because both base images are current releases, the frontend image runs `apk upgrade` to pick up
Alpine fixes published after its base image, and the backend image has pip removed from the
runtime layer. A finding would stop the job before `docker push`, so a vulnerable image never
reaches GHCR or the cluster. Trivy also scans the Terraform and Kubernetes manifests
(`trivy config`); the accepted exceptions are listed with reasons in [.trivyignore](../.trivyignore).

Further layers: pip-audit and npm audit (0 known vulnerabilities), Pod Security "restricted" on the
namespace ([14-pod-security](evidence/08-kubernetes/14-pod-security.png)), a NetworkPolicy that only
lets the backend reach PostgreSQL ([13-networkpolicy](evidence/08-kubernetes/13-networkpolicy.png)),
and GitHub OIDC for AWS so no AWS keys are stored in GitHub.

## M7 Terraform

Code: [terraform/](../terraform). VPC `10.40.0.0/16` over two availability zones (2 public + 2 private
subnets, Internet Gateway, NAT gateway), an EKS cluster with a managed node group (2 × t3.medium in
the private subnets), EKS add-ons (VPC CNI with NetworkPolicy, CoreDNS, kube-proxy, Pod Identity,
EBS CSI driver, metrics-server), S3 remote state, and the GitHub OIDC deploy role.

| Criterion | Evidence |
| :--- | :--- |
| Valid HCL, `terraform init` | [01-init-validate](evidence/07-terraform/01-init-validate.png): init, `fmt -check`, `validate` succeed; the same checks run in CI on every push |
| `terraform.tfvars.example`, no credentials committed | [terraform.tfvars.example](../terraform/terraform.tfvars.example); `*.tfvars`, state and `backend.hcl` are git-ignored; gitleaks finds nothing |

## M8 Kubernetes + Helm

Chart: [helm/bloodlink/](../helm/bloodlink). Local cluster: kind (1 control plane + 1 worker) with
ingress-nginx and metrics-server, built by [scripts/kind-up.ps1](../scripts/kind-up.ps1).

| Criterion | Evidence |
| :--- | :--- |
| `k8s/namespace.yaml` applies | [01-namespace](evidence/08-kubernetes/01-namespace.png) |
| Chart with `Chart.yaml`, `values.yaml`, templates | [08-chart-files](evidence/08-kubernetes/08-chart-files.png): file list and `helm lint` clean |
| `helm upgrade --install` works | [02-helm-list](evidence/08-kubernetes/02-helm-list.png), [04-helm-upgrade](evidence/10-live-demo/04-helm-upgrade.png) |
| Backend and frontend with 2+ replicas | [03-pods-running](evidence/08-kubernetes/03-pods-running.png), [06-workloads](evidence/08-kubernetes/06-workloads.png) |
| ClusterIP Services | [04-services](evidence/08-kubernetes/04-services.png) |
| Ingress `/` → frontend, `/api` → backend | [05-ingress](evidence/08-kubernetes/05-ingress.png) |
| All pods Running | [03-pods-running](evidence/08-kubernetes/03-pods-running.png) |
| App through the Ingress hostname | [09-app-via-ingress](evidence/08-kubernetes/09-app-via-ingress.png) at http://bloodlink.localhost |

Beyond the minimum:

- `helm test` checks the release from inside the cluster: [07-helm-test](evidence/08-kubernetes/07-helm-test.png)
- HorizontalPodAutoscaler under load, **2 → 4 → 6** replicas: [10-hpa-before-load](evidence/08-kubernetes/10-hpa-before-load.png), [11-hpa-load-start](evidence/08-kubernetes/11-hpa-load-start.png), [12-hpa-scaled-up](evidence/08-kubernetes/12-hpa-scaled-up.png)
- NetworkPolicy: only pods labelled as database clients of this release reach PostgreSQL: [13-networkpolicy](evidence/08-kubernetes/13-networkpolicy.png)
- Pod Security "restricted": a privileged pod is rejected: [14-pod-security](evidence/08-kubernetes/14-pod-security.png)
- PostgreSQL StatefulSet with a PersistentVolume, PodDisruptionBudget, nightly backup CronJob ([07-backup](evidence/11-troubleshooting/07-backup.png)), database password generated into a Secret, never in Git

## M9 Observability

kube-prometheus-stack ([monitoring/kube-prometheus-stack-values.yaml](../monitoring/kube-prometheus-stack-values.yaml)).
The chart ships a ServiceMonitor, 7 alert rules and the Grafana dashboard, so monitoring is
deployed together with the application.

| Criterion | Evidence |
| :--- | :--- |
| `/metrics` returns Prometheus format | [01-metrics-endpoint](evidence/09-observability/01-metrics-endpoint.png): HTTP metrics plus business metrics (`bloodlink_units_available{blood_group}`, expiring units, requests by status) |
| Prometheus scrapes the app | [02-prometheus-targets](evidence/09-observability/02-prometheus-targets.png): every backend pod **UP** |
| Grafana installed | [06-monitoring-stack](evidence/09-observability/06-monitoring-stack.png) |
| Panels with live data | [05-grafana-dashboard](evidence/09-observability/05-grafana-dashboard.png) |

The dashboard ("BloodLink - Blood Bank Overview", 14 panels in 3 rows) shows stock per blood group, units
expiring soon, fulfilment time, requests per second, error rate, p95 latency, CPU, memory and HPA
replicas. The load test spike, the scale-out to 6 replicas and the database outage from the
troubleshooting lab are all visible in it.

Alerts: [03-prometheus-alerts](evidence/09-observability/03-prometheus-alerts.png). The rules are
loaded and real ones are firing: `BloodLinkCriticalStock` (A-, B- and AB- are below 5 units) and
`BloodLinkEmergencyBacklog`. Query example: [04-prometheus-query](evidence/09-observability/04-prometheus-query.png).

![Grafana](evidence/09-observability/05-grafana-dashboard.png)

## M10 Live demo: commit → pipeline → deployment

The change: commit `e6491bf` "Show build commit in API and UI" passes the commit SHA into both
image builds; the page footer and `GET /` show which commit is running.

| Step | Evidence |
| :--- | :--- |
| Before: the cluster runs the previous release | [01-before-ui](evidence/10-live-demo/01-before-ui.png), [02-before-release](evidence/10-live-demo/02-before-release.png) |
| Commit pushed, pipeline green, images on GHCR | [03-pipeline-green](evidence/10-live-demo/03-pipeline-green.png) |
| `helm upgrade --set image.tag=<sha>` | [04-helm-upgrade](evidence/10-live-demo/04-helm-upgrade.png): revision 2, both Deployments on the new SHA, the backend reports `GIT_SHA=e6491bf…` |
| After: the app shows the new build | [05-after-ui](evidence/10-live-demo/05-after-ui.png), [06-after-footer](evidence/10-live-demo/06-after-footer.png): footer reads `Build e6491bf` |

The rollout uses `maxUnavailable: 0`, so users are served during the whole update.

## Troubleshooting lab

Each failure was caused on purpose with the manifests in [troubleshooting/](../troubleshooting) and
fixed with the steps in [RUNBOOK.md](RUNBOOK.md).

| Scenario | Symptom | Fix |
| :--- | :--- | :--- |
| 1. Image tag does not exist | [01a](evidence/11-troubleshooting/01a-imagepull-symptom.png) `ErrImagePull` / `ImagePullBackOff`, event says `not found` | [01b](evidence/11-troubleshooting/01b-imagepull-fix.png) point at a SHA the pipeline pushed |
| 2. Service selects no pods | [02a](evidence/11-troubleshooting/02a-no-endpoints-symptom.png) endpoints `<none>`, selector `component=api` vs pods `component=backend` | [02b](evidence/11-troubleshooting/02b-no-endpoints-fix.png) patch the selector, endpoints appear |
| 3. Database down | [03a](evidence/11-troubleshooting/03a-db-outage-symptom.png) backend `0/1` (readiness 503) but **not restarted**, API 503 | [03b](evidence/11-troubleshooting/03b-db-outage-fix.png) PostgreSQL back, pods Ready by themselves, data intact |
| 4. Wrong password in the Secret | [04a](evidence/11-troubleshooting/04a-bad-secret-symptom.png) new pod `Init:Error`, `password authentication failed`; old pods keep serving (200) | [04b](evidence/11-troubleshooting/04b-bad-secret-fix.png) `helm upgrade --reuse-values` rebuilds the Secret, rollout completes |
| 5. Out of memory | [05a](evidence/11-troubleshooting/05a-oom-symptom.png) `OOMKilled`, exit code 137, limit 64Mi | [05b](evidence/11-troubleshooting/05b-oom-fix.png) limit sized to real usage |
| 6. Bad release | [06a](evidence/11-troubleshooting/06a-bad-release.png) `helm upgrade` fails, users still served | [06b](evidence/11-troubleshooting/06b-rollback.png) `helm rollback`, previous SHA restored |
| Backup | [07-backup](evidence/11-troubleshooting/07-backup.png) `pg_dump` from the CronJob onto the backup volume | Restore steps in the runbook |

Real incidents met while building the project (not staged) are written up in the runbook as well:
Grafana OOM-killed under load, the kind control plane losing leader election on a slow disk, and a
full disk stopping Docker.
