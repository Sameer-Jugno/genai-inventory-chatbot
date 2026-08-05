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

variable "bedrock_claude_inference_profile_id" {
  description = "Bedrock inference profile ID used for invoking the Claude model."

  type = string

  default = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
}

variable "bedrock_claude_foundation_model_id" {
  description = "Bedrock foundation model ID for the Claude model."

  type = string

  default = "anthropic.claude-sonnet-4-5-20250929-v1:0"
}

variable "bedrock_titan_embedding_model_id" {
  description = "Bedrock foundation model ID for the Titan Embeddings V2 model."

  type = string

  default = "amazon.titan-embed-text-v2:0"
}

variable "common_tags" {
  description = "Common tags applied to all supported AWS resources."

  type = map(string)

  default = {}
}