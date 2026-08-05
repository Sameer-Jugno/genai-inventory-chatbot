output "ecs_task_execution_role_arn" {
  description = "ARN of the ECS task execution IAM role."

  value = aws_iam_role.ecs_task_execution.arn
}

output "ecs_task_role_arn" {
  description = "ARN of the ECS task IAM role used by the application containers."

  value = aws_iam_role.ecs_task.arn
}

output "lambda_execution_role_arn" {
  description = "ARN of the Lambda execution IAM role."

  value = aws_iam_role.lambda_execution.arn
}