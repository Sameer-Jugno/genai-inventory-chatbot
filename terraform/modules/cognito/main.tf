/*
Purpose:
Creates the Amazon Cognito User Pool and User Pool Client used for
authentication in the CandyWagon chat application.

This module is a deliberate addition beyond the client architecture diagram,
which shows no authentication in front of the internet-facing ALB. See
docs/DECISIONS.md (ADR-001) for the reasoning and the alternatives rejected.

Deliberately excluded:
- Identity Pool: Not required because the application does not provide direct AWS resource access to authenticated users.
- MFA: Omitted for this training POC to keep the authentication flow simple.
- SES: Omitted intentionally so Cognito uses its built-in email delivery, avoiding SES sandbox configuration.
*/

locals {
  user_pool_name        = "${var.project_name}-${var.environment}-users"
  user_pool_client_name = "${var.project_name}-${var.environment}-chat-app-client"
}

resource "aws_cognito_user_pool" "this" {
  name = local.user_pool_name

  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]

  password_policy {
    minimum_length    = 8
    require_uppercase = true
    require_lowercase = true
    require_numbers   = true
    require_symbols   = false
  }

  admin_create_user_config {
    allow_admin_create_user_only = true
  }

  # Deliberately disabled for this POC to simplify teardown.
  # Production environments should enable deletion protection.
  deletion_protection = "INACTIVE"

  # No email_configuration block is defined intentionally.
  # Cognito will use its built-in email delivery service, avoiding
  # SES configuration for this small-scale training project.

  tags = merge(
    var.common_tags,
    {
      Name = local.user_pool_name
    }
  )
}

# USER_PASSWORD_AUTH sends the password over TLS directly to Cognito.
# This is an accepted tradeoff for this small-scale training POC.
# A production system should use ALLOW_USER_SRP_AUTH instead, which
# never transmits the password itself.
resource "aws_cognito_user_pool_client" "this" {
  name         = local.user_pool_client_name
  user_pool_id = aws_cognito_user_pool.this.id

  generate_secret = false

  explicit_auth_flows = [
    "ALLOW_USER_PASSWORD_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH"
  ]
}