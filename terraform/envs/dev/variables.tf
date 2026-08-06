# ---------------------------------------------------------------------------
# Safe defaults — fine before account access
# ---------------------------------------------------------------------------

variable "project_name" {
  description = "Short project name used in AWS resource names."
  type        = string
  default     = "inventory-planner"
}

variable "environment" {
  description = "Deployment environment name."
  type        = string
  default     = "dev"
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC."
  type        = string
  default     = "10.0.0.0/16"
}

variable "public_subnet_cidrs" {
  description = "CIDR blocks for the two public subnets (ALB requires two AZs)."
  type        = list(string)
  default = [
    "10.0.0.0/24",
    "10.0.1.0/24"
  ]
}

variable "private_subnet_cidr" {
  description = "CIDR block for the single private subnet."
  type        = string
  default     = "10.0.10.0/24"
}

variable "common_tags" {
  description = "Tags applied to all supported resources via the provider default_tags and module tags."
  type        = map(string)

  default = {
    Project     = "inventory-planner"
    Environment = "dev"
    ManagedBy   = "terraform"
  }
}

# ---------------------------------------------------------------------------
# PLACEHOLDERS — replace after AWS account access
# See terraform.tfvars.example for where to put real values.
# ---------------------------------------------------------------------------

variable "aws_region" {
  description = "AWS region for this stack. Confirm which region the training account uses and which Bedrock models are available there."
  type        = string
  # PLACEHOLDER — update after account access
  default = "us-east-1"
}

variable "aws_profile" {
  description = "Named AWS CLI profile for this account. Empty string uses the default credential chain."
  type        = string
  # PLACEHOLDER — set to your profile name after `aws configure` / SSO login
  default = ""
}

variable "availability_zones" {
  description = "Exactly two AZs in aws_region. Must exist in the chosen region (e.g. us-east-1a, us-east-1b)."
  type        = list(string)

  # PLACEHOLDER — update to match the real region after account access
  default = [
    "us-east-1a",
    "us-east-1b"
  ]

  validation {
    condition     = length(var.availability_zones) == 2
    error_message = "Exactly two Availability Zones must be provided."
  }
}

variable "groq_model_id" {
  description = "Groq chat/extraction model ID."
  type        = string
  default     = "llama-3.3-70b-versatile"
}

variable "hf_embed_model_id" {
  description = "Hugging Face embedding model ID (feature-extraction)."
  type        = string
  default     = "BAAI/bge-large-en-v1.5"
}

variable "enable_iam" {
  description = "Create IAM roles/policies. Requires iam:CreateRole. Keep false until the lead grants IAM permissions."
  type        = bool
  default     = false
}

variable "enable_phase2" {
  description = "Create OpenSearch Serverless + ingestion Lambda. Requires enable_iam and a built dist/ingestion.zip."
  type        = bool
  default     = false

  validation {
    condition     = !var.enable_phase2 || var.enable_iam
    error_message = "enable_phase2 requires enable_iam = true (Lambda/ECS roles must exist for AOSS data-access principals)."
  }
}

variable "enable_phase3" {
  description = "Create ECS Fargate chat service and forward ALB traffic. Requires enable_phase2 and chat_container_image."
  type        = bool
  default     = false

  validation {
    condition     = !var.enable_phase3 || var.enable_phase2
    error_message = "enable_phase3 requires enable_phase2 = true (chat retrieves from OpenSearch)."
  }
}

variable "chat_container_image" {
  description = "ECR image URI for the chat service (repo:tag). Required when enable_phase3 is true."
  type        = string
  default     = ""

  validation {
    condition     = !var.enable_phase3 || length(trimspace(var.chat_container_image)) > 0
    error_message = "chat_container_image must be set when enable_phase3 = true."
  }
}

variable "opensearch_index" {
  description = "OpenSearch index name for inventory documents."
  type        = string
  default     = "inventory-items"
}

variable "opensearch_bootstrap_principal_arns" {
  description = "Extra IAM principal ARNs allowed to manage the inventory index (e.g. developer user for create_opensearch_index.py)."
  type        = list(string)
  default     = []
}
