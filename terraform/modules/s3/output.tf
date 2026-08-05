output "uploads_bucket_name" {
  description = "Name of the uploads S3 bucket."

  value = aws_s3_bucket.this["uploads"].id
}

output "uploads_bucket_arn" {
  description = "ARN of the uploads S3 bucket."

  value = aws_s3_bucket.this["uploads"].arn
}

output "images_bucket_name" {
  description = "Name of the images S3 bucket."

  value = aws_s3_bucket.this["images"].id
}

output "images_bucket_arn" {
  description = "ARN of the images S3 bucket."

  value = aws_s3_bucket.this["images"].arn
}