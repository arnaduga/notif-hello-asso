output "lambda_function_name" {
  description = "Name of the deployed Lambda function"
  value       = aws_lambda_function.api_processor.function_name
}

output "s3_results_bucket_name" {
  description = "Name of the S3 bucket storing processing results"
  value       = aws_s3_bucket.results_bucket.id
}

output "sns_topic_arn" { # AJOUTÉ
  description = "ARN of the SNS topic for notifications"
  value       = aws_sns_topic.results_notification.arn
}

output "cloudwatch_log_group" {
  description = "Name of the CloudWatch Log Group for Lambda logs"
  value       = aws_cloudwatch_log_group.lambda_logs.name
}
