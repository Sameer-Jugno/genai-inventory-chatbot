variable "project_name" {
  description = "Name of the project used for naming AWS resources."
  type        = string
}

variable "environment" {
  description = "Deployment environment (e.g., dev, test, prod)."
  type        = string
}

variable "vpc_id" {
  description = "ID of the VPC where the Application Load Balancer will be deployed."
  type        = string
}

variable "public_subnet_ids" {
  description = "List of public subnet IDs where the Application Load Balancer will be deployed."
  type        = list(string)
}

variable "common_tags" {
  description = "Common tags applied to all supported AWS resources."
  type        = map(string)
  default     = {}
}

variable "enable_forward" {
  description = "When true, forward HTTP to the chat target group (Phase 3 ECS). When false, return 503."
  type        = bool
  default     = false
}