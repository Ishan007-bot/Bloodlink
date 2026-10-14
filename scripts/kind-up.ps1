<#
.SYNOPSIS
  Local Kubernetes for BloodLink: kind cluster + ingress-nginx + metrics-server +
  kube-prometheus-stack + the BloodLink Helm release.

.EXAMPLE
  ./scripts/kind-up.ps1 -Tag 873c6cb4d726b479065ac15dc8ab7ec932d8f09c
  # Tag = the git commit SHA whose images CI pushed to GHCR.
#>
param(
    [Parameter(Mandatory = $true)][string]$Tag,
    [string]$Registry = "ghcr.io/ishan007-bot"
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

$IngressNginx = "controller-v1.15.1"
$MetricsServer = "v0.9.0"
$PromStack = "92.3.1"

function Step($text) { Write-Host "`n==> $text" -ForegroundColor Cyan }
# Windows PowerShell does not stop on a failing native command, so check exit codes explicitly.
function Check() { if ($LASTEXITCODE -ne 0) { throw "command failed with exit code $LASTEXITCODE" } }

if (-not (kind get clusters | Select-String -Quiet "^bloodlink$")) {
    Step "Creating kind cluster"
    kind create cluster --config "$root/k8s/kind-config.yaml"; Check
}
kubectl config use-context kind-bloodlink | Out-Null

Step "ingress-nginx $IngressNginx"
kubectl apply -f "https://raw.githubusercontent.com/kubernetes/ingress-nginx/$IngressNginx/deploy/static/provider/kind/deploy.yaml"; Check
# Run the controller on the node whose ports 80/443 are mapped to the host.
kubectl patch deployment ingress-nginx-controller -n ingress-nginx --patch-file "$root/k8s/ingress-nginx-kind-patch.yaml"; Check
kubectl rollout status deployment/ingress-nginx-controller -n ingress-nginx --timeout=300s; Check

Step "metrics-server $MetricsServer (needed by the HPA)"
kubectl apply -f "https://github.com/kubernetes-sigs/metrics-server/releases/download/$MetricsServer/components.yaml"; Check
# kind's kubelets use self-signed serving certificates.
$msArgs = kubectl get deployment metrics-server -n kube-system -o jsonpath='{.spec.template.spec.containers[0].args}'
if ($msArgs -notmatch "kubelet-insecure-tls") {
    # A patch file avoids Windows PowerShell stripping the quotes from inline JSON.
    kubectl patch deployment metrics-server -n kube-system --type=json --patch-file "$root/k8s/metrics-server-kind-patch.json"; Check
}
kubectl rollout status deployment/metrics-server -n kube-system --timeout=300s; Check

Step "kube-prometheus-stack $PromStack (Prometheus, Grafana, Alertmanager)"
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts --force-update | Out-Null
helm upgrade --install kube-prometheus-stack prometheus-community/kube-prometheus-stack `
    --version $PromStack -n monitoring --create-namespace `
    -f "$root/monitoring/kube-prometheus-stack-values.yaml" --wait --timeout 15m; Check

Step "BloodLink $Tag"
kubectl apply -f "$root/k8s/namespace.yaml"; Check
helm upgrade --install bloodlink "$root/helm/bloodlink" -n bloodlink `
    -f "$root/helm/bloodlink/values-kind.yaml" `
    --set image.registry=$Registry --set image.tag=$Tag `
    --wait --timeout 10m; Check
helm test bloodlink -n bloodlink; Check

Step "Done"
kubectl get pods,svc,ingress,hpa -n bloodlink
Write-Host "`nOpen http://bloodlink.localhost" -ForegroundColor Green
