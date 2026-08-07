/*
Purpose:
Creates the networking resources required to expose the Inventory Planner chat
application through an internet-facing Application Load Balancer (ALB).

NOTE:
The target group is intentionally created without registered targets until
Phase 3 (`enable_forward = true`) registers the ECS Fargate service.

When enable_forward is false the listener returns 503. When true it forwards
to the target group used by terraform/modules/ecs_chat.
*/

locals {
  alb_name          = "${var.project_name}-${var.environment}-alb"
  security_group    = "${var.project_name}-${var.environment}-alb-sg"
  target_group_name = "${var.project_name}-${var.environment}-tg"
}

resource "aws_security_group" "alb" {
  name        = local.security_group
  description = "Security group for the Application Load Balancer."
  vpc_id      = var.vpc_id

  ingress {
    description = "Allow HTTP traffic from the Internet."
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "Allow outbound traffic to application targets."
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(
    var.common_tags,
    {
      Name = local.security_group
    }
  )
}

resource "aws_lb" "this" {
  name               = local.alb_name
  internal           = false
  load_balancer_type = "application"

  security_groups = [
    aws_security_group.alb.id
  ]

  subnets = var.public_subnet_ids

  tags = merge(
    var.common_tags,
    {
      Name = local.alb_name
    }
  )
}

# Target group exists before ECS so Phase 3 can register tasks without
# recreating the ALB listener dependency graph.
resource "aws_lb_target_group" "this" {
  name        = local.target_group_name
  port        = 8000
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = var.vpc_id

  # Keep short so single-task Fargate rollouts are not blocked for 5 minutes.
  deregistration_delay = 30

  health_check {
    enabled             = true
    path                = "/"
    protocol            = "HTTP"
    interval            = 30
    timeout             = 5
    healthy_threshold   = 3
    unhealthy_threshold = 3
    matcher             = "200"
  }

  tags = merge(
    var.common_tags,
    {
      Name = local.target_group_name
    }
  )
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.this.arn
  port              = 80
  protocol          = "HTTP"

  dynamic "default_action" {
    for_each = var.enable_forward ? [1] : []
    content {
      type             = "forward"
      target_group_arn = aws_lb_target_group.this.arn
    }
  }

  dynamic "default_action" {
    for_each = var.enable_forward ? [] : [1]
    content {
      type = "fixed-response"

      fixed_response {
        content_type = "text/plain"
        message_body = "Service not yet deployed"
        status_code  = "503"
      }
    }
  }

  tags = merge(
    var.common_tags,
    {
      Name = "${var.project_name}-${var.environment}-http-listener"
    }
  )
}