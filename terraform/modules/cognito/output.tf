output "user_pool_id" {
  description = "The ID of the Amazon Cognito User Pool."

  value = aws_cognito_user_pool.this.id
}

output "user_pool_arn" {
  description = "The Amazon Resource Name (ARN) of the Amazon Cognito User Pool."

  value = aws_cognito_user_pool.this.arn
}

output "user_pool_client_id" {
  description = "The ID of the Amazon Cognito User Pool Client used by the chat application."

  value = aws_cognito_user_pool_client.this.id
}