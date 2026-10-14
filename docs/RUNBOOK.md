# BloodLink runbook

How to diagnose and fix the failures this system is most likely to have. Each scenario can be
reproduced on purpose (manifests in [`troubleshooting/`](../troubleshooting)) and lists
**symptom → where to look → cause → fix**. Screenshots of every scenario being run are in
[EVIDENCE.md](EVIDENCE.md).

All commands assume the app runs in namespace `bloodlink`:

```powershell
kubectl config set-context --current --namespace=bloodlink
```

## First five commands for any incident

```powershell
kubectl get pods -o wide                         # what is not Running / not READY?
kubectl get events --sort-by=.lastTimestamp       # what did Kubernetes just try and fail?
kubectl describe pod <pod>                       # per-pod events, probe failures, exit codes
kubectl logs <pod> [-c <container>] [--previous] # application output (previous = before the last crash)
kubectl get endpoints                            # does each Service actually point at pods?
```

---

## 1. Image cannot be pulled (`ImagePullBackOff`)

**Reproduce:** `kubectl apply -f troubleshooting/01-broken-image.yaml`

| | |
| :--- | :--- |
| Symptom | Pod stuck in `ErrImagePull`, then `ImagePullBackOff`; it never starts |
| Look at | `kubectl describe pod -l app=lab-broken-image` → Events: `Failed to pull image ... not found` |
| Cause | The tag `does-not-exist` was never pushed (typo, failed CI run, or wrong registry path) |
| Fix | Point at a tag CI actually pushed: `kubectl set image deployment/lab-broken-image api=ghcr.io/ishan007-bot/bloodlink-backend:<sha>`. For real releases, deploy only through Helm with the SHA of a green pipeline |

Clean up: `kubectl delete -f troubleshooting/01-broken-image.yaml`

## 2. Service has no endpoints

**Reproduce:** `kubectl apply -f troubleshooting/02-broken-service.yaml`

| | |
| :--- | :--- |
| Symptom | Requests to the Service fail, although every pod is `Running` |
| Look at | `kubectl get endpoints lab-broken-service` → `<none>`; `kubectl get pods --show-labels` |
| Cause | The Service selects `app.kubernetes.io/component=api`; the backend pods are labelled `component=backend`. No labels match → no endpoints → no traffic |
| Fix | Correct the selector (patch file avoids shell quoting issues): `kubectl patch svc lab-broken-service --patch-file troubleshooting/02-fix-service.patch.yaml`; `kubectl get endpoints` now lists pod IPs |

Clean up: `kubectl delete -f troubleshooting/02-broken-service.yaml`

## 3. Database outage: readiness, not liveness

**Reproduce:** `kubectl scale statefulset bloodlink-postgres --replicas=0`

| | |
| :--- | :--- |
| Symptom | Backend pods become `0/1` (NotReady) but **do not restart**; the UI shows "API unreachable" |
| Look at | `kubectl describe pod -l app.kubernetes.io/component=backend` → `Readiness probe failed: ... statuscode: 503`; `kubectl get endpoints bloodlink-backend` is empty |
| Cause | `/ready` checks the database; `/health` does not. Failing readiness removes pods from the Service; liveness keeps passing, so Kubernetes correctly does **not** restart a healthy process that is only waiting for its database |
| Fix | `kubectl scale statefulset bloodlink-postgres --replicas=1`. The backend turns Ready again by itself, with no restarts and no data loss (the PersistentVolume kept the data) |

## 4. Wrong database password in the Secret

**Reproduce:**

```powershell
kubectl patch secret bloodlink-db --patch-file troubleshooting/04-bad-db-password.patch.yaml
kubectl rollout restart deployment/bloodlink-backend
```

| | |
| :--- | :--- |
| Symptom | New backend pods stay in `Init:CrashLoopBackOff`; **the old pods keep serving**, so users see no outage |
| Look at | `kubectl logs <new-pod> -c migrate` → `password authentication failed for user "bloodlink"` |
| Cause | The Secret's `database-url` no longer matches the password PostgreSQL was initialised with. The rollout uses `maxUnavailable: 0`, so Kubernetes never removes a working pod before its replacement is Ready |
| Fix | Re-render the Secret from the stored password: `helm upgrade bloodlink helm/bloodlink -n bloodlink --reuse-values` (the chart rebuilds `database-url` from the `password` key). The failing init containers retry, pick up the corrected value, and the rollout completes on its own |

## 5. Container killed for using too much memory (`OOMKilled`)

**Reproduce:** `kubectl apply -f troubleshooting/03-oom-killed.yaml`

| | |
| :--- | :--- |
| Symptom | `CrashLoopBackOff`, restart count climbing |
| Look at | `kubectl describe pod -l app=lab-oom` → `Last State: Terminated, Reason: OOMKilled, Exit Code: 137` |
| Cause | The process allocates ~200 MB but the container's memory limit is 64 Mi; the kernel kills it |
| Fix | Size the limit to real usage (measure with `kubectl top pod`): `kubectl set resources deployment lab-oom --limits=memory=320Mi --requests=memory=256Mi` |

Clean up: `kubectl delete -f troubleshooting/03-oom-killed.yaml`

## 6. Bad release: roll back with Helm

| | |
| :--- | :--- |
| Symptom | A new revision does not become ready (`helm upgrade --wait` times out) or the app misbehaves after a deploy |
| Look at | `helm history bloodlink`, `kubectl rollout status deployment/bloodlink-backend` |
| Cause | Whatever changed in the last revision (image tag, values) |
| Fix | `helm rollback bloodlink <previous-revision> --wait`. Because of `maxUnavailable: 0`, the previous pods keep serving until the rollback completes |

## 7. Alerts

The chart ships these Prometheus alert rules (`helm/bloodlink/templates/prometheusrule.yaml`):

| Alert | Fires when | First action |
| :--- | :--- | :--- |
| `BloodLinkBackendDown` | no backend pod scraped for 2 min | `kubectl get pods`; scenarios 1, 3, 4 |
| `BloodLinkHighErrorRate` | more than 5 % of requests return 5xx for 5 min | backend logs; check `/ready` |
| `BloodLinkSlowAPI` | p95 latency above 1 s for 10 min | Grafana latency panel; `kubectl top pods`; HPA status |
| `BloodLinkCriticalStock` | a blood group below half the safety stock for 10 min | call donors of that group |
| `BloodLinkUniversalDonorLow` | O- below 3 units | O- donor drive: it is the emergency blood |
| `BloodLinkEmergencyBacklog` | an emergency request open for 15 min | process the queue; source compatible units |
| `BloodLinkUnitsExpiringSoon` | more than 20 units expire within 7 days | offer units to partner hospitals |

## 8. Real incidents met while building BloodLink

These were not staged: they happened on the local cluster and were diagnosed and fixed as below.

### Grafana restarting: OOMKilled

| | |
| :--- | :--- |
| Symptom | During the HPA load test Grafana became unreachable; `kubectl get pods -n monitoring` showed `kube-prometheus-stack-grafana` at `2/3` with 10+ restarts |
| Look at | `kubectl get pod -n monitoring -l app.kubernetes.io/name=grafana -o jsonpath='{..lastState.terminated.reason}'` → `OOMKilled`; its limit was `256Mi` |
| Cause | Grafana 12 with the default dashboards uses about 250 MiB, so normal load crossed the limit |
| Fix | Limit raised to `512Mi` (request `192Mi`) in `monitoring/kube-prometheus-stack-values.yaml`, applied with `helm upgrade`; no restarts since |

### Control plane restarting: "Leaderelection lost"

| | |
| :--- | :--- |
| Symptom | `kube-scheduler` and `kube-controller-manager` in `CrashLoopBackOff`; a Job ran past its `activeDeadlineSeconds` and the HPA stopped reacting; `kubectl` briefly returned `Forbidden` and TLS timeouts |
| Look at | `kubectl logs -n kube-system kube-scheduler-<node> --previous` → `Error retrieving lease lock ... context deadline exceeded`, `Leaderelection lost`; etcd logs → hundreds of `apply request took too long` (up to 1.5 s, expected 100 ms) |
| Cause | etcd waits for every write to reach the disk (fsync). The laptop disk was slow (almost full, and Docker's disk image lives on it), so the API server missed the 5-second lease deadline and the components restarted themselves. Each restart added load, so they kept failing. Without the controller-manager, nothing enforces Job deadlines or runs the HPA |
| Fix | For the throwaway local cluster: etcd `--unsafe-no-fsync=true` and longer leases (`--leader-elect-lease-duration=60s`, `--leader-elect-renew-deadline=40s`) in `k8s/kind-config.yaml`. Slow etcd requests went from 368 per 10 minutes to 0. Real clusters (EKS) run etcd on managed, fast storage and keep fsync on |

### Docker stopped: disk full

| | |
| :--- | :--- |
| Symptom | `docker ps` hung, then "Docker Desktop is unable to start"; a test run failed with `sqlite3.OperationalError: database or disk is full` |
| Look at | `Get-PSDrive C` → 0 GB free; `docker system df` → 14 GB of build cache |
| Cause | Repeated image builds left build cache in Docker's disk image, and interrupted `terraform init` runs left 2.9 GB of provider downloads in the temp folder |
| Fix | `docker builder prune -af`, removed the leftover provider files, restarted Docker Desktop (`wsl --shutdown` first). The cluster came back with its data, because it lives on PersistentVolumes |

## Backups and restore

A CronJob runs `pg_dump` nightly onto the `backups` volume (newest 7 kept). Run one now, then restore:

```powershell
kubectl create job --from=cronjob/bloodlink-backup backup-now
kubectl logs job/backup-now
# Restore from inside the database pod, where /backups is mounted read-only:
kubectl exec -it bloodlink-postgres-0 -- sh -c 'gunzip -c /backups/<file>.sql.gz | psql -U bloodlink -d bloodlink'
```
