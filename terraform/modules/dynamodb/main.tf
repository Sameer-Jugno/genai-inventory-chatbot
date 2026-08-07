/*
Purpose:
Creates the Amazon DynamoDB table used to store chat session history for
the Inventory Planner application.

This module is a deliberate addition beyond the client architecture diagram.
Conversation state cannot live in container memory because ECS Fargate tasks
are replaceable. See docs/DECISIONS.md (ADR-002).

NOTE:
TTL is enabled on the expires_at attribute — application code is
responsible for setting this value on write (e.g., session creation
time + 30 days); Terraform only enables the feature, it does not set
expiry values on individual items.

Access patterns:
  1) Fetch one session's turns: Query base table by session_id, ordered by timestamp
  2) List a user's sessions: Query GSI user_sub-index by user_sub, newest first
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

  attribute {
    name = "user_sub"
    type = "S"
  }

  global_secondary_index {
    name            = "user_sub-index"
    hash_key        = "user_sub"
    range_key       = "timestamp"
    projection_type = "ALL"
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
