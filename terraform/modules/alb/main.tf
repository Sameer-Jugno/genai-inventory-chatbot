/*
Purpose:
Creates the networking resources required to expose the CandyWagon chat
application through an internet-facing Application Load Balancer (ALB).

NOTE:
The target group is intentionally created without registered targets.
ECS Fargate service registration occurs in Module 4.1.

The listener intentionally returns a temporary 503 fixed response.
Module 4.1 will update the listener to forward traffic to the target
group once the ECS Fargate service has been deployed.
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

# This target group currently has no registered targets.
# ECS Fargate service registration happens in Module 4.1.
# This resource exists now so the listener below has a valid,
# real target group to route to once traffic is actually flowing.
resource "aws_lb_target_group" "this" {
  name        = local.target_group_name
  port        = 8000
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = var.vpc_id

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

# Temporary placeholder default action.
# Module 4.1 will update this to forward to the target group
# above once the ECS Fargate service exists.
# This must be changed manually (or via a follow-up Terraform
# update) — it will not resolve itself.
resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.this.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type = "fixed-response"

    fixed_response {
      content_type = "text/plain"
      message_body = "Service not yet deployed"
      status_code  = "503"
    }
  }

  tags = merge(
    var.common_tags,
    {
      Name = "${var.project_name}-${var.environment}-http-listener"
    }
  )
}