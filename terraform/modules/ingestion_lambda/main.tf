/*
Purpose:
Deploys the inventory ingestion Lambda: S3 uploads/ trigger, SQS DLQ,
CloudWatch log group, and permission for S3 to invoke the function.

The execution role is owned by the iam module (passed in as lambda_role_arn).
Package the function with scripts/build_ingestion_package.sh before apply.
*/

locals {
  function_name = "${var.project_name}-${var.environment}-ingestion"
  dlq_name      = "${var.project_name}-${var.environment}-ingestion-dlq"
}

resource "aws_cloudwatch_log_group" "ingestion" {
  name              = "/aws/lambda/${local.function_name}"
  retention_in_days = var.log_retention_days

  tags = merge(
    var.common_tags,
    {
      Name = local.function_name
    }
  )
}

resource "aws_sqs_queue" "dlq" {
  name                      = local.dlq_name
  message_retention_seconds = 1209600 # 14 days

  tags = merge(
    var.common_tags,
    {
      Name = local.dlq_name
    }
  )
}

resource "aws_cloudwatch_metric_alarm" "dlq_messages" {
  alarm_name          = "${local.dlq_name}-messages-visible"
  alarm_description   = "Inventory ingestion failures are waiting in the DLQ."
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    QueueName = aws_sqs_queue.dlq.name
  }

  tags = var.common_tags
}

resource "aws_lambda_function" "ingestion" {
  function_name = local.function_name
  role          = var.lambda_role_arn
  handler       = "services.ingestion.handler.handler"
  runtime       = "python3.12"

  filename         = var.package_path
  source_code_hash = var.source_code_hash

  memory_size = var.memory_size
  timeout     = var.timeout_seconds

  dead_letter_config {
    target_arn = aws_sqs_queue.dlq.arn
  }

  environment {
    variables = {
      DATA_BUCKET_NAME       = var.data_bucket_name
      UPLOADS_PREFIX         = var.uploads_prefix
      IMAGES_PREFIX          = var.images_prefix
      OPENSEARCH_ENDPOINT   = var.opensearch_endpoint
      OPENSEARCH_INDEX      = var.opensearch_index
      GROQ_MODEL_ID         = var.groq_model_id
      HF_EMBED_MODEL_ID     = var.hf_embed_model_id
      PROVIDER_SECRETS_ARN  = var.provider_secrets_arn
      AWS_REGION_NAME       = var.aws_region
      MAX_UPLOAD_BYTES      = tostring(var.max_upload_bytes)
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.ingestion
  ]

  tags = merge(
    var.common_tags,
    {
      Name = local.function_name
    }
  )
}

resource "aws_lambda_permission" "allow_s3" {
  statement_id  = "AllowS3InvokeIngestion"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ingestion.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = var.data_bucket_arn
}

# Notification is owned here so trigger + function stay in one module.
# Filter on uploads/ only — never images/ (ADR-004 / ADR-007).
resource "aws_s3_bucket_notification" "uploads" {
  bucket = var.data_bucket_id

  lambda_function {
    lambda_function_arn = aws_lambda_function.ingestion.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = var.uploads_prefix
  }

  depends_on = [
    aws_lambda_permission.allow_s3
  ]
}
