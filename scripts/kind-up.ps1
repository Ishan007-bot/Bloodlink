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

if (-not (kind get clusters | Select-String -Quiet "^bloodlink$")) {
    Step "Creating kind cluster"
    kind create cluster --config "$root/k8s/kind-config.yaml"
}
kubectl config use-context kind-bloodlink | Out-Null

Step "ingress-nginx $IngressNginx"
kubectl apply -f "https://raw.githubusercontent.com/kubernetes/ingress-nginx/$IngressNginx/deploy/static/provider/kind/deploy.yaml"
kubectl wait -n ingress-nginx --for=condition=ready pod -l app.kubernetes.io/component=controller --timeout=300s

Step "metrics-server $MetricsServer (needed by the HPA)"
kubectl apply -f "https://github.com/kubernetes-sigs/metrics-server/releases/download/$MetricsServer/components.yaml"
# kind's kubelets use self-signed serving certificates.
kubectl patch deployment metrics-server -n kube-system --type=json `
    -p '[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]'
kubectl rollout status deployment/metrics-server -n kube-system --timeout=300s

Step "kube-prometheus-stack $PromStack (Prometheus, Grafana, Alertmanager)"
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts --force-update | Out-Null
helm upgrade --install kube-prometheus-stack prometheus-community/kube-prometheus-stack `
    --version $PromStack -n monitoring --create-namespace `
    -f "$root/monitoring/kube-prometheus-stack-values.yaml" --wait --timeout 15m

Step "BloodLink $Tag"
kubectl apply -f "$root/k8s/namespace.yaml"
helm upgrade --install bloodlink "$root/helm/bloodlink" -n bloodlink `
    -f "$root/helm/bloodlink/values-kind.yaml" `
    --set image.registry=$Registry --set image.tag=$Tag `
    --wait --timeout 10m
helm test bloodlink -n bloodlink

Step "Done"
kubectl get pods,svc,ingress,hpa -n bloodlink
Write-Host "`nOpen http://bloodlink.localhost" -ForegroundColor Green
