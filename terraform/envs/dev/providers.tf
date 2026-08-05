provider "aws" {
  region = var.aws_region

  # Optional. Leave empty to use the default credential chain
  # (env vars, shared credentials file, SSO, etc.).
  profile = var.aws_profile != "" ? var.aws_profile : null

  default_tags {
    tags = var.common_tags
  }
}
