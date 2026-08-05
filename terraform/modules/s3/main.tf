/*
Purpose:
Creates the Amazon S3 buckets required by the CandyWagon POC for
inventory uploads and image storage.

NOTE:
Buckets are provisioned here only — S3 event notifications/Lambda
triggers are configured in the lambda module once it exists, not here,
to keep storage and compute concerns separate.
*/

locals {
  buckets = {
    uploads = "${var.project_name}-${var.environment}-uploads"
    images  = "${var.project_name}-${var.environment}-images"
  }
}

resource "aws_s3_bucket" "this" {
  for_each = local.buckets

  bucket = each.value

  tags = merge(
    var.common_tags,
    {
      Name = "${var.project_name}-${var.environment}-${each.key}"
    }
  )
}

resource "aws_s3_bucket_public_access_block" "this" {
  for_each = local.buckets

  bucket = aws_s3_bucket.this[each.key].id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
resource "aws_s3_bucket_versioning" "this" {
  for_each = local.buckets

  bucket = aws_s3_bucket.this[each.key].id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "this" {
  for_each = local.buckets

  bucket = aws_s3_bucket.this[each.key].id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}