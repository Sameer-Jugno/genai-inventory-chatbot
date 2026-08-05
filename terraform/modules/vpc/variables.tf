variable "project_name" {
  description = "Name of the project used for naming AWS resources."
  type        = string
}

variable "environment" {
  description = "Deployment environment (e.g., dev, test, prod)."
  type        = string
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC."
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "List of exactly two Availability Zones used for the public subnets."

  type = list(string)

  validation {
    condition     = length(var.availability_zones) == 2
    error_message = "Exactly two Availability Zones must be provided."
  }
}

variable "public_subnet_cidrs" {
  description = "CIDR blocks for the two public subnets."

  type = list(string)

  default = [
    "10.0.0.0/24",
    "10.0.1.0/24"
  ]

  validation {
    condition     = length(var.public_subnet_cidrs) == 2
    error_message = "Exactly two public subnet CIDR blocks must be provided."
  }
}

variable "private_subnet_cidr" {
  description = "CIDR block for the single private subnet."
  type        = string
  default     = "10.0.10.0/24"
}

variable "common_tags" {
  description = "Common tags applied to all supported AWS resources."
  type        = map(string)
  default     = {}
}