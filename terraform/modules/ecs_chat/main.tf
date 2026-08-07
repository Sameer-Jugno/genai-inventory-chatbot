/*
Purpose:
Runs the Inventory Planner chat application (Chainlit + Bedrock agent) on
ECS Fargate behind the existing ALB target group.

Assumptions:
- Image is already pushed to the Phase 1 ECR repository.
- IAM roles exist (enable_iam) and OpenSearch is available (enable_phase2).
- Single private subnet is intentional for this POC (see VPC module).
*/

locals {
  cluster_name = "${var.project_name}-${var.environment}-chat"
  service_name = "${var.project_name}-${var.environment}-chat"
  log_group    = "/ecs/${var.project_name}-${var.environment}-chat"
}

resource "aws_cloudwatch_log_group" "chat" {
  name              = local.log_group
  retention_in_days = 14

  tags = merge(var.common_tags, { Name = local.log_group })
}

resource "aws_security_group" "chat" {
  name        = "${var.project_name}-${var.environment}-chat-sg"
  description = "ECS Fargate tasks for the chat application."
  vpc_id      = var.vpc_id

  ingress {
    description     = "ALB to Chainlit"
    from_port       = var.container_port
    to_port         = var.container_port
    protocol        = "tcp"
    security_groups = [var.alb_security_group_id]
  }

  egress {
    description = "Outbound to Bedrock, OpenSearch, S3, DynamoDB via NAT"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.common_tags, { Name = "${var.project_name}-${var.environment}-chat-sg" })
}

resource "aws_ecs_cluster" "chat" {
  name = local.cluster_name

  setting {
    name  = "containerInsights"
    value = "disabled"
  }

  tags = merge(var.common_tags, { Name = local.cluster_name })
}

resource "aws_ecs_task_definition" "chat" {
  family                   = local.service_name
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.cpu
  memory                   = var.memory
  execution_role_arn       = var.execution_role_arn
  task_role_arn            = var.task_role_arn

  container_definitions = jsonencode([
    {
      name      = "chat"
      image     = var.container_image
      essential = true
      portMappings = [
        {
          containerPort = var.container_port
          hostPort      = var.container_port
          protocol      = "tcp"
        }
      ]
      environment = [
        { name = "AWS_REGION", value = var.aws_region },
        { name = "OPENSEARCH_ENDPOINT", value = var.opensearch_endpoint },
        { name = "OPENSEARCH_INDEX", value = var.opensearch_index },
        { name = "GROQ_MODEL_ID", value = var.groq_model_id },
        { name = "HF_EMBED_MODEL_ID", value = var.hf_embed_model_id },
        { name = "PROVIDER_SECRETS_ARN", value = var.provider_secrets_arn },
        { name = "DYNAMODB_TABLE_NAME", value = var.dynamodb_table_name },
        { name = "DATA_BUCKET_NAME", value = var.data_bucket_name },
        { name = "IMAGES_PREFIX", value = var.images_prefix },
        { name = "COGNITO_USER_POOL_ID", value = var.cognito_user_pool_id },
        { name = "COGNITO_APP_CLIENT_ID", value = var.cognito_app_client_id },
      ]
      # Chainlit requires this env var at process start (before app code runs).
      secrets = [
        {
          name      = "CHAINLIT_AUTH_SECRET"
          valueFrom = "${var.provider_secrets_arn}:CHAINLIT_AUTH_SECRET::"
        }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.chat.name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "chat"
        }
      }
      healthCheck = {
        command     = ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:${var.container_port}/', timeout=5)\" || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 60
      }
    }
  ])

  tags = merge(var.common_tags, { Name = local.service_name })
}

resource "aws_ecs_service" "chat" {
  name            = local.service_name
  cluster         = aws_ecs_cluster.chat.id
  task_definition = aws_ecs_task_definition.chat.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = [var.private_subnet_id]
    security_groups  = [aws_security_group.chat.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = var.target_group_arn
    container_name   = "chat"
    container_port   = var.container_port
  }

  # Single-task POC: allow a new task to start while the old one drains,
  # otherwise ALB deregistration can leave runningCount at 0.
  deployment_minimum_healthy_percent = 0
  deployment_maximum_percent         = 200

  depends_on = [aws_ecs_task_definition.chat]

  tags = merge(var.common_tags, { Name = local.service_name })
}
