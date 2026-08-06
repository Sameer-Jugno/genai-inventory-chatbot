/*
Purpose:
Creates an AWS Secrets Manager secret for Groq + Hugging Face API keys.
The secret *value* is pushed out-of-band by scripts/put_provider_secrets.sh
so keys never live in Terraform state or tfvars.
*/

variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "common_tags" {
  type    = map(string)
  default = {}
}

locals {
  secret_name = "${var.project_name}-${var.environment}-provider-keys"
}

resource "aws_secretsmanager_secret" "provider_keys" {
  name                    = local.secret_name
  description             = "Groq + Hugging Face API keys for inventory planner"
  recovery_window_in_days = 0

  tags = merge(
    var.common_tags,
    {
      Name = local.secret_name
    }
  )
}

# Placeholder so the secret exists before the first put-secret-value.
resource "aws_secretsmanager_secret_version" "provider_keys_placeholder" {
  secret_id = aws_secretsmanager_secret.provider_keys.id
  secret_string = jsonencode({
    GROQ_API_KEY = "REPLACE_ME"
    HF_TOKEN     = "REPLACE_ME"
  })

  lifecycle {
    ignore_changes = [secret_string]
  }
}

output "secret_arn" {
  value = aws_secretsmanager_secret.provider_keys.arn
}

output "secret_name" {
  value = aws_secretsmanager_secret.provider_keys.name
}
