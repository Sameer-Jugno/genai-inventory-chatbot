/*
Purpose:
Creates the Amazon ECR repository holding the container image for the
Inventory Planner chat application (Chainlit interface + Bedrock Converse agent) that
runs on ECS Fargate.

NOTE:
Immutable tags force every deployment to reference a unique image tag (Git
short SHA), so an ECS task definition is always an exact, reproducible
pointer to one image rather than a moving target like ":latest".

force_delete defaults to true as a POC-only convenience so `terraform
destroy` succeeds while images are still present in the repository.
*/

locals {
  repository_name = "${var.project_name}-${var.environment}-chat-app"
}

resource "aws_ecr_repository" "this" {
  name                 = local.repository_name
  image_tag_mutability = var.image_tag_mutability
  force_delete         = var.force_delete

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }

  tags = merge(
    var.common_tags,
    {
      Name = local.repository_name
    }
  )
}

# ECR lifecycle rules have no awareness of which images ECS is currently
# running. Retaining the 10 most recent tagged images is comfortably above
# the POC deployment cadence, so a running task cannot lose its image.
resource "aws_ecr_lifecycle_policy" "this" {
  repository = aws_ecr_repository.this.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Expire untagged images after 1 day"

        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = 1
        }

        action = {
          type = "expire"
        }
      },
      {
        rulePriority = 2
        description  = "Retain only the most recent 10 tagged images"

        selection = {
          tagStatus      = "tagged"
          tagPatternList = ["*"]
          countType      = "imageCountMoreThan"
          countNumber    = 10
        }

        action = {
          type = "expire"
        }
      }
    ]
  })
}