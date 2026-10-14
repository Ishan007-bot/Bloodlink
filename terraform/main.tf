data "aws_availability_zones" "available" {
  state = "available"
  filter {
    name   = "opt-in-status"
    values = ["opt-in-not-required"]
  }
}

locals {
  azs = slice(data.aws_availability_zones.available.names, 0, var.availability_zone_count)
}

# ---------------------------------------------------------------- network
# Public subnets hold the NAT gateway and the internet-facing load balancer.
# Private subnets hold the worker nodes, which reach the internet through the NAT gateway.
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 6.0"

  name = "${var.cluster_name}-vpc"
  cidr = var.vpc_cidr
  azs  = local.azs

  public_subnets  = [for i, _ in local.azs : cidrsubnet(var.vpc_cidr, 8, i)]     # 10.40.0.0/24, 10.40.1.0/24
  private_subnets = [for i, _ in local.azs : cidrsubnet(var.vpc_cidr, 4, i + 1)] # 10.40.16.0/20, 10.40.32.0/20

  enable_nat_gateway   = true
  single_nat_gateway   = true # one NAT keeps the classroom bill low; use one per AZ in production
  enable_dns_hostnames = true
  enable_dns_support   = true

  # Tags the AWS load-balancer integration uses to pick subnets.
  public_subnet_tags = {
    "kubernetes.io/role/elb" = 1
  }
  private_subnet_tags = {
    "kubernetes.io/role/internal-elb" = 1
  }
}

# ---------------------------------------------------------------- EKS
module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 21.0"

  name               = var.cluster_name
  kubernetes_version = var.kubernetes_version

  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets

  # Public API endpoint so kubectl and GitHub Actions can reach it; nodes stay private.
  endpoint_public_access       = true
  endpoint_public_access_cidrs = var.api_allowed_cidrs

  # The identity that runs `terraform apply` becomes cluster admin.
  enable_cluster_creator_admin_permissions = true

  addons = {
    vpc-cni = {
      before_compute = true
      # Turns on enforcement of Kubernetes NetworkPolicy objects (the chart restricts Postgres).
      configuration_values = jsonencode({ enableNetworkPolicy = "true" })
    }
    eks-pod-identity-agent = {
      before_compute = true
    }
    kube-proxy = {}
    coredns    = {}
    aws-ebs-csi-driver = {
      # PersistentVolumeClaims (PostgreSQL data) need the EBS CSI driver.
      pod_identity_association = [{
        role_arn        = module.ebs_csi_pod_identity.iam_role_arn
        service_account = "ebs-csi-controller-sa"
      }]
    }
    # CPU/memory metrics for `kubectl top` and the Horizontal Pod Autoscaler.
    metrics-server = {}
  }

  eks_managed_node_groups = {
    default = {
      ami_type       = "AL2023_x86_64_STANDARD"
      instance_types = var.node_instance_types
      min_size       = var.node_min_size
      desired_size   = var.node_desired_size
      max_size       = var.node_max_size
      labels = {
        workload = "general"
      }
    }
  }

  access_entries = {
    # GitHub Actions deploy job (see github-oidc.tf).
    github_deploy = {
      principal_arn = aws_iam_role.github_deploy.arn
      policy_associations = {
        admin = {
          policy_arn = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"
          access_scope = {
            type = "cluster"
          }
        }
      }
    }
  }
}

# IAM role for the EBS CSI driver, bound to its service account with EKS Pod Identity.
module "ebs_csi_pod_identity" {
  source  = "terraform-aws-modules/eks-pod-identity/aws"
  version = "~> 2.0"

  name                      = "${var.cluster_name}-ebs-csi"
  attach_aws_ebs_csi_policy = true
}
