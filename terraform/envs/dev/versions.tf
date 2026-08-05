terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  # Local state for the training POC. Switch to an S3 backend once the AWS
  # account exists and a remote state bucket has been agreed with the team.
}
