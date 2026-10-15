<#
.SYNOPSIS
  Installs the platform add-ons and BloodLink on the EKS cluster created by terraform/.

  Run after `terraform apply` (see docs/DEPLOYMENT.md):
    ./scripts/eks-up.ps1 -Tag <git-sha>
#>
param(
    [Parameter(Mandatory = $true)][string]$Tag,
    [string]$Registry = "ghcr.io/ishan007-bot",
    [string]$Region = "ap-southeast-2",
    [string]$ClusterName = "bloodlink-eks"
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

$IngressNginxChart = "4.15.1"
$PromStack = "92.3.1"

function Step($text) { Write-Host "`n==> $text" -ForegroundColor Cyan }
function Check() { if ($LASTEXITCODE -ne 0) { throw "command failed with exit code $LASTEXITCODE" } }

Step "kubeconfig for $ClusterName"
aws eks update-kubeconfig --region $Region --name $ClusterName; Check
kubectl get nodes -o wide; Check

Step "gp3 StorageClass (EBS CSI driver)"
# EKS ships a non-default gp2 class; make encrypted gp3 the default instead.
# (gp2 may not exist on newer clusters, so a failure here is fine.)
$ErrorActionPreference = "Continue"
kubectl annotate storageclass gp2 storageclass.kubernetes.io/is-default-class=false --overwrite 2>&1 | Out-Null
$ErrorActionPreference = "Stop"
kubectl apply -f "$root/k8s/storageclass-gp3.yaml"; Check

Step "ingress-nginx $IngressNginxChart behind an AWS Network Load Balancer"
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx --force-update | Out-Null
helm upgrade --install ingress-nginx ingress-nginx/ingress-nginx --version $IngressNginxChart `
    -n ingress-nginx --create-namespace `
    --set controller.service.annotations."service\.beta\.kubernetes\.io/aws-load-balancer-type"=nlb `
    --set controller.service.annotations."service\.beta\.kubernetes\.io/aws-load-balancer-scheme"=internet-facing `
    --set controller.metrics.enabled=true `
    --wait --timeout 10m; Check

Step "kube-prometheus-stack $PromStack"
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts --force-update | Out-Null
helm upgrade --install kube-prometheus-stack prometheus-community/kube-prometheus-stack `
    --version $PromStack -n monitoring --create-namespace `
    -f "$root/monitoring/kube-prometheus-stack-values.yaml" --wait --timeout 15m; Check

Step "BloodLink $Tag"
kubectl apply -f "$root/k8s/namespace.yaml"; Check
helm upgrade --install bloodlink "$root/helm/bloodlink" -n bloodlink `
    -f "$root/helm/bloodlink/values-eks.yaml" `
    --set image.registry=$Registry --set image.tag=$Tag `
    --wait --timeout 15m; Check
helm test bloodlink -n bloodlink; Check

Step "Done"
kubectl get pods,svc,ingress,hpa,pvc -n bloodlink
$lb = kubectl get svc ingress-nginx-controller -n ingress-nginx -o jsonpath='{.status.loadBalancer.ingress[0].hostname}'
Write-Host "`nApp: http://$lb  (DNS can take a few minutes to resolve)" -ForegroundColor Green
