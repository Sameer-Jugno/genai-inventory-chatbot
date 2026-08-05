/*
Purpose:
Creates the IAM roles and policies required by the Inventory Planner compute
components (ECS Fargate and Lambda) to access AWS services provisioned
by earlier infrastructure modules.

Assumptions to verify once a real AWS account is available:
- The Claude inference profile ID format and identifier are assumed to
  be correct. Confirm against the target AWS account and region before
  production deployment.
- Titan Embeddings V2 is assumed to support direct foundation-model
  invocation without an inference profile. Confirm this behavior once
  tested against a live AWS account.
*/

data "aws_caller_identity" "current" {}

data "aws_region" "current" {}

locals {
  ecs_task_execution_role_name = "${var.project_name}-${var.environment}-ecs-task-execution-role"
  ecs_task_role_name           = "${var.project_name}-${var.environment}-ecs-task-role"
  lambda_execution_role_name   = "${var.project_name}-${var.environment}-lambda-execution-role"

  claude_inference_profile_arn = "arn:aws:bedrock:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:inference-profile/${var.bedrock_claude_inference_profile_id}"

  claude_foundation_model_arn = "arn:aws:bedrock:${data.aws_region.current.region}::foundation-model/${var.bedrock_claude_foundation_model_id}"

  titan_foundation_model_arn = "arn:aws:bedrock:${data.aws_region.current.region}::foundation-model/${var.bedrock_titan_embedding_model_id}"
}

resource "aws_iam_role" "ecs_task_execution" {
  name = local.ecs_task_execution_role_name

  assume_role_policy = jsonencode({
    Version = "2012-10-17"

    Statement = [
      {
        Effect = "Allow"

        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }

        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = merge(
    var.common_tags,
    {
      Name = local.ecs_task_execution_role_name
    }
  )
}

resource "aws_iam_role_policy_attachment" "ecs_task_execution" {
  role       = aws_iam_role.ecs_task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role" "ecs_task" {
  name = local.ecs_task_role_name

  assume_role_policy = jsonencode({
    Version = "2012-10-17"

    Statement = [
      {
        Effect = "Allow"

        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }

        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = merge(
    var.common_tags,
    {
      Name = local.ecs_task_role_name
    }
  )
}

resource "aws_iam_role_policy" "ecs_task" {
  name = "${local.ecs_task_role_name}-policy"
  role = aws_iam_role.ecs_task.id

  policy = jsonencode({
    Version = "2012-10-17"

    Statement = [
      {
        Sid    = "InvokeClaudeInferenceProfile"
        Effect = "Allow"

        Action = [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream"
        ]

        Resource = local.claude_inference_profile_arn
      },
      {
        Sid    = "InvokeClaudeFoundationModelViaInferenceProfile"
        Effect = "Allow"

        Action = [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream"
        ]

        Resource = local.claude_foundation_model_arn

        Condition = {
          StringLike = {
            "bedrock:InferenceProfileArn" = local.claude_inference_profile_arn
          }
        }
      },
      {
        Sid    = "DynamoDBSessionAccess"
        Effect = "Allow"

        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:Query"
        ]

        Resource = var.dynamodb_table_arn
      },
      # Cognito end-user auth happens in the client. The app verifies JWTs using
      # Cognito's public JWKS endpoint — that needs no cognito-idp IAM permissions.
      # See docs/DECISIONS.md (ADR-001).
      {
        Sid    = "ReadProcessedImages"
        Effect = "Allow"

        Action = [
          "s3:GetObject"
        ]

        Resource = "${var.data_bucket_arn}/images/*"
      }

      # TODO: Add OpenSearch permissions when Module 2.1
      # provisions the OpenSearch domain.
    ]
  })
}
resource "aws_iam_role" "lambda_execution" {
  name = local.lambda_execution_role_name

  assume_role_policy = jsonencode({
    Version = "2012-10-17"

    Statement = [
      {
        Effect = "Allow"

        Principal = {
          Service = "lambda.amazonaws.com"
        }

        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = merge(
    var.common_tags,
    {
      Name = local.lambda_execution_role_name
    }
  )
}

resource "aws_iam_role_policy_attachment" "lambda_execution" {
  role       = aws_iam_role.lambda_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "lambda_execution" {
  name = "${local.lambda_execution_role_name}-policy"
  role = aws_iam_role.lambda_execution.id

  policy = jsonencode({
    Version = "2012-10-17"

    Statement = [
      {
        Sid    = "InvokeClaudeInferenceProfile"
        Effect = "Allow"

        Action = [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream"
        ]

        Resource = local.claude_inference_profile_arn
      },
      {
        Sid    = "InvokeClaudeFoundationModelViaInferenceProfile"
        Effect = "Allow"

        Action = [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream"
        ]

        Resource = local.claude_foundation_model_arn

        Condition = {
          StringLike = {
            "bedrock:InferenceProfileArn" = local.claude_inference_profile_arn
          }
        }
      },
      # Assumption: Titan Embeddings V2 supports direct foundation-model
      # invocation without requiring an inference profile.
      # Verify this against a live AWS account before production use.
      {
        Sid    = "InvokeTitanEmbeddings"
        Effect = "Allow"

        Action = [
          "bedrock:InvokeModel"
        ]

        Resource = local.titan_foundation_model_arn
      },
      {
        Sid    = "ReadRawUploads"
        Effect = "Allow"

        Action = [
          "s3:GetObject"
        ]

        Resource = "${var.data_bucket_arn}/uploads/*"
      },
      {
        Sid    = "WriteProcessedImages"
        Effect = "Allow"

        Action = [
          "s3:PutObject"
        ]

        Resource = "${var.data_bucket_arn}/images/*"
      }

      # TODO: Add OpenSearch permissions when Module 2.1
      # provisions the OpenSearch domain.
    ]
  })
}