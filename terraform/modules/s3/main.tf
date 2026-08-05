/*
Purpose:
Creates one private Amazon S3 data bucket for the Inventory Planner POC.

Object prefixes separate the two data lifecycles:
- uploads/ — raw CSV, PDF, or scraped HTML placed by an administrator
- images/  — image assets written by the ingestion Lambda and read by the app

The future S3 notification must filter on the uploads/ prefix. Without that
filter, images written by Lambda would trigger the ingestion function again.

The AWS account ID makes the bucket name globally unique and deterministic.
See docs/DECISIONS.md (ADR-004).
*/

data "aws_caller_identity" "current" {}

locals {
  bucket_name = "${var.project_name}-${var.environment}-data-${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3_bucket" "this" {
  bucket = local.bucket_name

  tags = merge(
    var.common_tags,
    {
      Name = local.bucket_name
    }
  )
}

resource "aws_s3_bucket_public_access_block" "this" {
  bucket = aws_s3_bucket.this.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
resource "aws_s3_bucket_versioning" "this" {
  bucket = aws_s3_bucket.this.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "this" {
  bucket = aws_s3_bucket.this.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}