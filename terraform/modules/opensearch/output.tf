output "collection_id" {
  description = "OpenSearch Serverless collection ID."
  value       = aws_opensearchserverless_collection.this.id
}

output "collection_arn" {
  description = "OpenSearch Serverless collection ARN."
  value       = aws_opensearchserverless_collection.this.arn
}

output "collection_name" {
  description = "OpenSearch Serverless collection name."
  value       = aws_opensearchserverless_collection.this.name
}

output "collection_endpoint" {
  description = "HTTPS endpoint for OpenSearch API calls."
  value       = aws_opensearchserverless_collection.this.collection_endpoint
}

output "dashboard_endpoint" {
  description = "OpenSearch Dashboards endpoint (if enabled)."
  value       = aws_opensearchserverless_collection.this.dashboard_endpoint
}
