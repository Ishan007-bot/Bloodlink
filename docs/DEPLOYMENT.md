# Deploying BloodLink

Every image is built and scanned by CI and tagged with the **git commit SHA** that produced it
(`ghcr.io/ishan007-bot/bloodlink-backend:<sha>`). Deploying means telling Helm which SHA to run.
The images are public on GHCR, so clusters pull them without credentials.

Tools: Docker Desktop, kubectl, Helm 3.14+ / 4, kind 0.24+, Terraform 1.10+, AWS CLI v2.

---

## A. Local Kubernetes (kind)

```powershell
$sha = git rev-parse HEAD          # any commit with a green pipeline
./scripts/kind-up.ps1 -Tag $sha
```

The script is idempotent and does, in order:

1. `kind create cluster --config k8s/kind-config.yaml` (1 control plane + 1 worker, host ports 80/443)
2. ingress-nginx (kind variant) and metrics-server (with `--kubelet-insecure-tls` for kind)
3. kube-prometheus-stack with `monitoring/kube-prometheus-stack-values.yaml`
4. `k8s/namespace.yaml` (Pod Security "restricted"), then
   `helm upgrade --install bloodlink helm/bloodlink -f helm/bloodlink/values-kind.yaml --set image.tag=$sha`
5. `helm test bloodlink`

Open **http://bloodlink.localhost** (browsers resolve `*.localhost` to 127.0.0.1).

Grafana and Prometheus:

```powershell
kubectl port-forward -n monitoring svc/kube-prometheus-stack-grafana 3001:80
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090
# Grafana user "admin"; password:
kubectl get secret -n monitoring kube-prometheus-stack-grafana -o jsonpath="{.data.admin-password}" |
  ForEach-Object { [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($_)) }
```

Upgrade to a newer commit: run the same `helm upgrade --install ... --set image.tag=<new-sha>`.
Roll back: `helm rollback bloodlink <revision> -n bloodlink`.

Remove everything: `kind delete cluster --name bloodlink`.

---

## B. AWS (Terraform + EKS)

> Cost: an EKS control plane, two t3.medium nodes, a NAT gateway and a load balancer are billed
> per hour (roughly USD 0.30/hour in ap-southeast-2). Destroy when finished.

### 1. Credentials

An IAM user or role with permissions for EC2/VPC, EKS, IAM, S3, KMS and CloudWatch Logs,
configured with `aws configure` (never committed). Check: `aws sts get-caller-identity`.

### 2. State bucket (once)

```powershell
terraform -chdir=terraform/bootstrap init
terraform -chdir=terraform/bootstrap apply          # prints state_bucket
Copy-Item terraform/backend.hcl.example terraform/backend.hcl   # put the bucket name in it
```

### 3. Network and cluster

```powershell
Copy-Item terraform/terraform.tfvars.example terraform/terraform.tfvars   # optional overrides
terraform -chdir=terraform init -backend-config=backend.hcl
terraform -chdir=terraform plan -out=tfplan
terraform -chdir=terraform apply tfplan             # ~15 minutes
```

Creates: VPC `10.40.0.0/16` over two AZs (2 public + 2 private subnets, Internet Gateway, one NAT
gateway), EKS cluster with a managed node group in the private subnets, add-ons (VPC CNI with
NetworkPolicy enforcement, CoreDNS, kube-proxy, EKS Pod Identity, EBS CSI driver, metrics-server),
and the GitHub Actions OIDC deploy role.

### 4. Platform and app

```powershell
./scripts/eks-up.ps1 -Tag (git rev-parse HEAD)
```

Configures kubectl, makes encrypted gp3 the default StorageClass, installs ingress-nginx behind an
AWS Network Load Balancer, kube-prometheus-stack, and BloodLink. The script prints the load
balancer's DNS name, which is where the app is served.

### 5. Continuous deployment from GitHub Actions

Set these **repository variables** (Settings → Secrets and variables → Actions → Variables):

| Variable | Value |
| :--- | :--- |
| `DEPLOY_EKS` | `true` |
| `AWS_DEPLOY_ROLE_ARN` | `terraform -chdir=terraform output -raw github_deploy_role_arn` |
| `AWS_REGION` | `ap-southeast-2` |
| `EKS_CLUSTER_NAME` | `bloodlink-eks` |

From then on every push to `main` that passes all checks runs the **Deploy to EKS** job:
OIDC → `aws eks update-kubeconfig` → `helm upgrade --install --set image.tag=<sha> --wait`.
No AWS access keys are stored in GitHub.

### 6. Tear down

```powershell
# Set DEPLOY_EKS to false first, so a push cannot redeploy.
helm uninstall bloodlink -n bloodlink                 # releases the EBS volumes
helm uninstall ingress-nginx -n ingress-nginx         # deletes the load balancer
helm uninstall kube-prometheus-stack -n monitoring
kubectl delete pvc --all -n bloodlink
terraform -chdir=terraform destroy
terraform -chdir=terraform/bootstrap destroy          # the state bucket, last
```

Uninstalling ingress-nginx first matters: its load balancer is created by Kubernetes, not
Terraform, and would otherwise keep the VPC's subnets in use and block `terraform destroy`.
