output "repository_url" {
  description = "The full URI of the Amazon ECR repository used for pushing and pulling container images."

  value = aws_ecr_repository.this.repository_url
}

output "repository_arn" {
  description = "The Amazon Resource Name (ARN) of the ECR repository."

  value = aws_ecr_repository.this.arn
}

output "repository_name" {
  description = "The name of the ECR repository."

  value = aws_ecr_repository.this.name
}