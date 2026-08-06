variable "project_name" {
  description = "Name of the project used for naming AWS resources."
  type        = string
}

variable "environment" {
  description = "Deployment environment (e.g., dev, test, prod)."
  type        = string
}

variable "aws_region" {
  description = "AWS region passed into the Lambda environment."
  type        = string
}

variable "lambda_role_arn" {
  description = "ARN of the IAM role assumed by the ingestion Lambda."
  type        = string
}

variable "package_path" {
  description = "Path to the ingestion deployment zip built by scripts/build_ingestion_package.sh."
  type        = string
}

variable "source_code_hash" {
  description = "Base64-encoded SHA256 of the deployment zip (pass from the env root so file hashing is gated by enable_phase2)."
  type        = string
}

variable "data_bucket_id" {
  description = "ID (name) of the shared data bucket."
  type        = string
}

variable "data_bucket_arn" {
  description = "ARN of the shared data bucket."
  type        = string
}

variable "data_bucket_name" {
  description = "Name of the shared data bucket (env var for the function)."
  type        = string
}

variable "uploads_prefix" {
  description = "S3 key prefix that triggers ingestion."
  type        = string
  default     = "uploads/"
}

variable "images_prefix" {
  description = "S3 key prefix where processed images are written."
  type        = string
  default     = "images/"
}

variable "opensearch_endpoint" {
  description = "OpenSearch collection HTTPS endpoint."
  type        = string
}

variable "opensearch_index" {
  description = "OpenSearch index name for inventory documents."
  type        = string
  default     = "inventory-items"
}

variable "groq_model_id" {
  description = "Groq model ID for extraction / chat."
  type        = string
  default     = "llama-3.3-70b-versatile"
}

variable "hf_embed_model_id" {
  description = "Hugging Face embedding model ID."
  type        = string
  default     = "BAAI/bge-large-en-v1.5"
}

variable "provider_secrets_arn" {
  description = "Secrets Manager ARN containing GROQ_API_KEY and HF_TOKEN."
  type        = string
}

variable "memory_size" {
  description = "Lambda memory in MB."
  type        = number
  default     = 2048
}

variable "timeout_seconds" {
  description = "Lambda timeout in seconds."
  type        = number
  default     = 900
}

variable "max_upload_bytes" {
  description = "Maximum S3 upload size accepted by the in-memory Lambda parser."
  type        = number
  default     = 134217728 # 128 MiB
}

variable "log_retention_days" {
  description = "CloudWatch log retention for the ingestion function."
  type        = number
  default     = 14
}

variable "common_tags" {
  description = "Common tags applied to all supported AWS resources."
  type        = map(string)
  default     = {}
}
