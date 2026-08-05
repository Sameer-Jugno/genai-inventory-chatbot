/*
Purpose:
Creates the Amazon DynamoDB table used to store chat session history for
the CandyWagon application.

NOTE:
TTL is enabled on the expires_at attribute — application code is
responsible for setting this value on write (e.g., session creation
time + 30 days); Terraform only enables the feature, it does not set
expiry values on individual items.

No secondary indexes are defined — the only access pattern (fetch by
session_id, ordered by timestamp) is fully served by the base table's
key schema.
*/

locals {
  table_name = "${var.project_name}-${var.environment}-sessions"
}

resource "aws_dynamodb_table" "this" {
  name         = local.table_name
  billing_mode = "PAY_PER_REQUEST"

  hash_key  = "session_id"
  range_key = "timestamp"

  attribute {
    name = "session_id"
    type = "S"
  }

  attribute {
    name = "timestamp"
    type = "N"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled = true
  }

  tags = merge(
    var.common_tags,
    {
      Name = local.table_name
    }
  )
}