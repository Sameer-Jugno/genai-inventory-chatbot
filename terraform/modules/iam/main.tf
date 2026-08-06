/*
Purpose:
Creates the IAM roles and policies required by the Inventory Planner compute
components (ECS Fargate and Lambda) to access AWS services provisioned
by earlier infrastructure modules.

Model inference uses external providers over HTTPS. Provider API keys are read
from AWS Secrets Manager at runtime.
*/

locals {
  ecs_task_execution_role_name = "${var.project_name}-${var.environment}-ecs-task-execution-role"
  ecs_task_role_name           = "${var.project_name}-${var.environment}-ecs-task-role"
  lambda_execution_role_name   = "${var.project_name}-${var.environment}-lambda-execution-role"
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

# Required so ECS can inject Secrets Manager values into the container env
# (CHAINLIT_AUTH_SECRET) at task start.
resource "aws_iam_role_policy" "ecs_task_execution_secrets" {
  name = "${local.ecs_task_execution_role_name}-secrets"
  role = aws_iam_role.ecs_task_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "ReadProviderSecretsForInjection"
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue"]
        Resource = var.provider_secrets_arn
      }
    ]
  })
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
        Sid    = "DynamoDBSessions"
        Effect = "Allow"
        Action = [
          "dynamodb:DeleteItem",
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:Query",
          "dynamodb:Scan",
          "dynamodb:UpdateItem"
        ]
        Resource = [
          var.dynamodb_table_arn,
          "${var.dynamodb_table_arn}/index/*",
        ]
      },
      {
        Sid      = "ReadImages"
        Effect   = "Allow"
        Action   = "s3:GetObject"
        Resource = "${var.data_bucket_arn}/images/*"
      },
      {
        Sid      = "ReadProviderSecrets"
        Effect   = "Allow"
        Action   = "secretsmanager:GetSecretValue"
        Resource = var.provider_secrets_arn
      },
      {
        Sid      = "CognitoUserPasswordLogin"
        Effect   = "Allow"
        Action   = [
          "cognito-idp:InitiateAuth",
          "cognito-idp:SignUp",
          "cognito-idp:AdminConfirmSignUp",
          "cognito-idp:AdminGetUser",
        ]
        Resource = "*"
      }
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
        Sid      = "ReadUploads"
        Effect   = "Allow"
        Action   = "s3:GetObject"
        Resource = "${var.data_bucket_arn}/uploads/*"
      },
      {
        Sid      = "WriteImages"
        Effect   = "Allow"
        Action   = "s3:PutObject"
        Resource = "${var.data_bucket_arn}/images/*"
      },
      {
        Sid      = "ReadProviderSecrets"
        Effect   = "Allow"
        Action   = "secretsmanager:GetSecretValue"
        Resource = var.provider_secrets_arn
      }
    ]
  })
}
