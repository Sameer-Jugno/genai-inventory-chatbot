output "function_name" {
  description = "Name of the ingestion Lambda function."
  value       = aws_lambda_function.ingestion.function_name
}

output "function_arn" {
  description = "ARN of the ingestion Lambda function."
  value       = aws_lambda_function.ingestion.arn
}

output "dlq_arn" {
  description = "ARN of the ingestion dead-letter queue."
  value       = aws_sqs_queue.dlq.arn
}

output "dlq_url" {
  description = "URL of the ingestion dead-letter queue."
  value       = aws_sqs_queue.dlq.url
}

output "log_group_name" {
  description = "CloudWatch log group for the ingestion function."
  value       = aws_cloudwatch_log_group.ingestion.name
}

output "dlq_alarm_name" {
  description = "CloudWatch alarm raised when failed ingestion messages are visible."
  value       = aws_cloudwatch_metric_alarm.dlq_messages.alarm_name
}
