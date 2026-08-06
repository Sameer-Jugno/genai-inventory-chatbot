/*
Purpose:
Provisions an OpenSearch Serverless VECTORSEARCH collection for the inventory
catalog (ADR-005).

Wired into terraform/envs/dev behind enable_phase2 (default false). Do not set
enable_phase2 until enable_iam is true and Phase 1 IAM apply has succeeded.

Index mappings are NOT created here — apply scripts/opensearch_index_mapping.json
via scripts/create_opensearch_index.py after the collection is active.

NOTE:
Serverless availability and billing mode vary by account. If apply fails because
VECTORSEARCH / Serverless is unavailable, fall back to a managed domain (document
in DECISIONS.md).
*/

locals {
  collection_name = "${var.project_name}-${var.environment}-inventory"
  # OpenSearch Serverless names: 3-32 chars, lowercase, alphanumeric + hyphen
}

resource "aws_opensearchserverless_security_policy" "encryption" {
  name = "${var.project_name}-${var.environment}-enc"
  type = "encryption"

  policy = jsonencode({
    Rules = [
      {
        ResourceType = "collection"
        Resource     = ["collection/${local.collection_name}"]
      }
    ]
    AWSOwnedKey = true
  })
}

resource "aws_opensearchserverless_security_policy" "network" {
  name = "${var.project_name}-${var.environment}-net"
  type = "network"

  policy = jsonencode([
    {
      Rules = [
        {
          ResourceType = "collection"
          Resource     = ["collection/${local.collection_name}"]
        },
        {
          ResourceType = "dashboard"
          Resource     = ["collection/${local.collection_name}"]
        }
      ]
      # POC: allow public access to the collection endpoint; tighten with VPC
      # endpoints when moving beyond training.
      AllowFromPublic = true
    }
  ])
}

resource "aws_opensearchserverless_collection" "this" {
  name = local.collection_name
  type = "VECTORSEARCH"

  depends_on = [
    aws_opensearchserverless_security_policy.encryption,
    aws_opensearchserverless_security_policy.network
  ]

  tags = merge(
    var.common_tags,
    {
      Name = local.collection_name
    }
  )
}

resource "aws_opensearchserverless_access_policy" "data" {
  name = "${var.project_name}-${var.environment}-data"
  type = "data"

  policy = jsonencode([
    {
      Rules = [
        {
          ResourceType = "index"
          Resource     = ["index/${local.collection_name}/*"]
          Permission = [
            "aoss:CreateIndex",
            "aoss:UpdateIndex",
            "aoss:DescribeIndex",
            "aoss:ReadDocument",
            "aoss:WriteDocument"
          ]
        },
        {
          ResourceType = "collection"
          Resource     = ["collection/${local.collection_name}"]
          Permission = [
            "aoss:CreateCollectionItems",
            "aoss:DescribeCollectionItems",
            "aoss:UpdateCollectionItems"
          ]
        }
      ]
      Principal = var.data_access_principal_arns
    }
  ])

  lifecycle {
    precondition {
      condition     = length(var.data_access_principal_arns) > 0
      error_message = "data_access_principal_arns must include at least the Lambda and ECS task role ARNs."
    }
  }
}
