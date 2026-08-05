output "alb_dns_name" {
  description = "DNS name of the Application Load Balancer."

  value = aws_lb.this.dns_name
}

output "alb_security_group_id" {
  description = "ID of the Application Load Balancer security group."

  value = aws_security_group.alb.id
}

output "target_group_arn" {
  description = "ARN of the Application Load Balancer target group."

  value = aws_lb_target_group.this.arn
}

output "listener_arn" {
  description = "ARN of the HTTP listener."

  value = aws_lb_listener.http.arn
}