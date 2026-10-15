# GitHub Actions authenticates to AWS with short-lived OIDC tokens, so no AWS access keys
# are stored in GitHub. Only jobs in this repository's "production" environment may
# assume the role.

resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
}

data "aws_iam_policy_document" "github_deploy_trust" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    # GitHub sends either the classic subject or, for repositories with immutable subjects
    # enabled, one that pins the owner and repository IDs (so a recreated repo cannot match).
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values = compact([
        "repo:${var.github_repository}:environment:${var.github_environment}",
        var.github_immutable_repository == "" ? "" : "repo:${var.github_immutable_repository}:environment:${var.github_environment}",
      ])
    }
  }
}

resource "aws_iam_role" "github_deploy" {
  name                 = "${var.cluster_name}-github-deploy"
  assume_role_policy   = data.aws_iam_policy_document.github_deploy_trust.json
  max_session_duration = 3600
}

# AWS-side permission is only "describe the cluster" (to build a kubeconfig);
# what the role may do inside Kubernetes is granted by the EKS access entry in main.tf.
data "aws_iam_policy_document" "github_deploy" {
  statement {
    actions   = ["eks:DescribeCluster"]
    resources = [module.eks.cluster_arn]
  }
}

resource "aws_iam_role_policy" "github_deploy" {
  name   = "describe-cluster"
  role   = aws_iam_role.github_deploy.id
  policy = data.aws_iam_policy_document.github_deploy.json
}
