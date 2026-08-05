output "bucket_name" {
  description = "Name of the shared data bucket containing uploads/ and images/ prefixes."
  value       = aws_s3_bucket.this.id
}

output "bucket_arn" {
  description = "ARN of the shared data bucket."
  value       = aws_s3_bucket.this.arn
}

output "uploads_prefix" {
  description = "Object-key prefix used for raw administrator uploads."
  value       = "uploads/"
}

output "images_prefix" {
  description = "Object-key prefix used for processed image assets."
  value       = "images/"
}