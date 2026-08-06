variable "project_name" {
  description = "Name of the project used for naming AWS resources."
  type        = string
}

variable "environment" {
  description = "Deployment environment (e.g., dev, test, prod)."
  type        = string
}

variable "dynamodb_table_arn" {
  description = "ARN of the DynamoDB sessions table."
  type        = string
}

variable "data_bucket_arn" {
  description = "ARN of the shared S3 data bucket containing uploads/ and images/ prefixes."
  type        = string
}

variable "provider_secrets_arn" {
  description = "ARN of the Secrets Manager secret containing external provider API keys."
  type        = string
}

variable "common_tags" {
  description = "Common tags applied to all supported AWS resources."

  type = map(string)

  default = {}
}