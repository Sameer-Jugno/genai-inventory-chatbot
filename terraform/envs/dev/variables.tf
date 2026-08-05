# ---------------------------------------------------------------------------
# Safe defaults — fine before account access
# ---------------------------------------------------------------------------

variable "project_name" {
  description = "Short project name used in AWS resource names."
  type        = string
  default     = "candywagon"
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
    Project     = "candywagon"
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

variable "bedrock_claude_inference_profile_id" {
  description = "Bedrock inference profile ID for Claude. Confirm in the account console after model access is granted."
  type        = string
  # PLACEHOLDER — verify against Bedrock console in the target account/region
  default = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
}

variable "bedrock_claude_foundation_model_id" {
  description = "Bedrock foundation model ID for Claude. Confirm in the account console after model access is granted."
  type        = string
  # PLACEHOLDER — verify against Bedrock console in the target account/region
  default = "anthropic.claude-sonnet-4-5-20250929-v1:0"
}

variable "bedrock_titan_embedding_model_id" {
  description = "Bedrock Titan Embeddings model ID used by the ingestion path."
  type        = string
  # PLACEHOLDER — verify against Bedrock console in the target account/region
  default = "amazon.titan-embed-text-v2:0"
}
