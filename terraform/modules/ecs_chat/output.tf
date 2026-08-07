output "cluster_name" {
  value = aws_ecs_cluster.chat.name
}

output "service_name" {
  value = aws_ecs_service.chat.name
}

output "security_group_id" {
  value = aws_security_group.chat.id
}

output "log_group_name" {
  value = aws_cloudwatch_log_group.chat.name
}
