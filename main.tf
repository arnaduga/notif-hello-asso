provider "aws" {
  region = var.aws_region

  default_tags {
    tags = local.default_tags
  }

}

locals {
  s3_bucket_name          = "${replace(var.project_prefix, "_", "-")}-bucket-${var.random_number}"
  lambda_function_name    = "${var.environment}-${replace(var.project_prefix, "_", "-")}-payments-extractor"
  clouwatch_loggroup_name = "/aws/lambda/${var.project_prefix}-log-group"
  sns_topic_name          = "${var.environment}-${replace(var.project_prefix, "_", "-")}-topic"
  default_tags = {
    context     = var.project_context
    environment = var.environment
    managed_by  = "Terraform"
  }
}


#############################
# Lambda Function Resources #
#############################

# Archive the Lambda function code
data "archive_file" "lambda_zip" {
  type        = "zip"
  source_dir  = "${path.module}/lambda"
  output_path = "${path.module}/lambda_function.zip"
}

# Lambda function
resource "aws_lambda_function" "api_processor" {
  function_name    = "${var.project_prefix}-extractor"
  description      = "Retrieves keys from Parameter Store, calls API, processes data, saves result to S3 and generates presigned URL"
  filename         = data.archive_file.lambda_zip.output_path
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256
  role             = aws_iam_role.lambda_role.arn
  handler          = "main.lambda_handler"
  runtime          = "python3.11"
  timeout          = 15
  memory_size      = 256
  architectures    = ["arm64"]

  environment {
    variables = {
      API_URL_PARAM_NAME           = aws_ssm_parameter.api_url.name
      API_URL_TOKEN_PARAM_NAME     = aws_ssm_parameter.api_url_token.name
      API_CLIENT_ID_PARAM_NAME     = aws_ssm_parameter.api_client_id.name
      API_CLIENT_SECRET_PARAM_NAME = aws_ssm_parameter.api_client_secret.name
      S3_BUCKET_NAME               = aws_s3_bucket.results_bucket.id
      PRESIGNED_URL_EXPIRATION     = tostring(var.presigned_url_expiration_seconds)
      ENVIRONMENT                  = var.environment
      SNS_TOPIC_ARN                = aws_sns_topic.results_notification.arn
      SUCCESS_SNS_SUBJECT_TEMPLATE = var.success_sns_subject_template
      ERROR_SNS_SUBJECT_TEMPLATE   = var.error_sns_subject_template

    }
  }

  depends_on = [
    aws_iam_role_policy_attachment.lambda_logs,
    aws_iam_role_policy_attachment.lambda_ssm,
    aws_iam_role_policy_attachment.lambda_s3,
    aws_iam_role_policy_attachment.lambda_sns,
    aws_cloudwatch_log_group.lambda_logs,
  ]
}

# CloudWatch Log Group for Lambda
resource "aws_cloudwatch_log_group" "lambda_logs" {
  name              = "/aws/lambda/${local.clouwatch_loggroup_name}"
  retention_in_days = 7
}

#######################
# IAM Role Resources #
#######################

# IAM role for Lambda
resource "aws_iam_role" "lambda_role" {
  name = "${var.project_prefix}-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

# CloudWatch Logs policy
resource "aws_iam_policy" "lambda_logging" {
  name        = "${var.project_prefix}-logging-policy"
  description = "IAM policy for logging from Lambda"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Effect   = "Allow"
        Resource = "${aws_cloudwatch_log_group.lambda_logs.arn}:*"
      }
    ]
  })
}

# Parameter Store access policy
resource "aws_iam_policy" "lambda_ssm" {
  name        = "${var.project_prefix}-ssm-policy"
  description = "IAM policy for accessing Parameter Store from Lambda"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = [
          "ssm:GetParameter",
          "ssm:GetParameters"
        ]
        Effect = "Allow"
        Resource = [
          aws_ssm_parameter.api_url.arn,
          aws_ssm_parameter.api_url_token.arn,
          aws_ssm_parameter.api_client_id.arn,
          aws_ssm_parameter.api_client_secret.arn
        ]
      }
    ]
  })
}

resource "aws_iam_policy" "lambda_s3" {
  name        = "${var.project_prefix}-s3-policy"
  description = "IAM policy for putting objects into S3 results bucket"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = [
          "s3:PutObject",
          "s3:GetObject"
        ]
        Effect   = "Allow"
        Resource = "${aws_s3_bucket.results_bucket.arn}/*"
      }
    ]
  })
}

resource "aws_iam_policy" "lambda_sns" {
  name        = "${local.sns_topic_name}-sns-policy"
  description = "IAM policy for publishing to SNS topic"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action   = "sns:Publish"
        Effect   = "Allow"
        Resource = aws_sns_topic.results_notification.arn
      }
    ]
  })
}

# Attach policies to role
resource "aws_iam_role_policy_attachment" "lambda_logs" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = aws_iam_policy.lambda_logging.arn
}

resource "aws_iam_role_policy_attachment" "lambda_ssm" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = aws_iam_policy.lambda_ssm.arn
}

resource "aws_iam_role_policy_attachment" "lambda_s3" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = aws_iam_policy.lambda_s3.arn
}

resource "aws_iam_role_policy_attachment" "lambda_sns" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = aws_iam_policy.lambda_sns.arn
}

#######################
# Parameter Store    #
#######################

resource "aws_ssm_parameter" "api_url" {
  name        = "/${var.environment}/${var.project_prefix}/api/url"
  description = "API URL for the Lambda function"
  type        = "String"
  value       = var.api_url
  tags = {
    Environment = var.environment
  }
}

resource "aws_ssm_parameter" "api_url_token" {
  name        = "/${var.environment}/${var.project_prefix}/api/url_token"
  description = "API token URL for the Lambda function"
  type        = "String"
  value       = var.api_url_token
  tags = {
    Environment = var.environment
  }
}

resource "aws_ssm_parameter" "api_client_id" {
  name        = "/${var.environment}/${var.project_prefix}/api/client_id"
  description = "API Client ID for the Lambda function"
  type        = "SecureString"
  value       = var.api_client_id
  tags = {
    Environment = var.environment
  }
}

resource "aws_ssm_parameter" "api_client_secret" {
  name        = "/${var.environment}/${var.project_prefix}/api/client_secret"
  description = "API Client secret for the Lambda function"
  type        = "SecureString"
  value       = var.api_client_secret
  tags = {
    Environment = var.environment
  }
}

#######################
# S3 Bucket for Results
#######################
resource "aws_s3_bucket" "results_bucket" {
  bucket = local.s3_bucket_name

  force_destroy = true

  tags = merge(
    {
      Name = local.s3_bucket_name
    }
  )
}

resource "aws_s3_bucket_lifecycle_configuration" "results_lifecycle" {
  bucket = aws_s3_bucket.results_bucket.id

  rule {
    id     = "expire-old-results"
    status = "Enabled"

    filter {
      prefix = "**/*"
    }

    expiration {
      days = 400
    }
  }

}

resource "aws_s3_bucket_public_access_block" "results_access_block" {
  bucket = aws_s3_bucket.results_bucket.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "results_versioning" {
  bucket = aws_s3_bucket.results_bucket.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "results_encryption" {
  bucket = aws_s3_bucket.results_bucket.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

#######################
# SNS Topic & Subscriptions
#######################
resource "aws_sns_topic" "results_notification" {
  name = "${var.environment}-${var.project_prefix}-topic"
  tags = merge(
    local.default_tags,
    {
      Name = "${var.environment}-${var.project_prefix}-topic"
    }
  )
}

# Souscription Email (conditionnelle)
resource "aws_sns_topic_subscription" "email_subscription" {
  for_each  = toset(var.notification_emails)
  topic_arn = aws_sns_topic.results_notification.arn
  protocol  = "email"
  endpoint  = each.value
}


#######################
# Lambda Trigger     #
#######################

# CloudWatch Event Rule to trigger Lambda on a schedule (optional)
resource "aws_cloudwatch_event_rule" "schedule" {
  count               = var.enable_scheduled_execution ? 1 : 0
  name                = "${var.project_prefix}-schedule"
  description         = "Schedule for triggering the Lambda function"
  schedule_expression = var.schedule_expression
}

resource "aws_cloudwatch_event_target" "lambda_target" {
  count     = var.enable_scheduled_execution ? 1 : 0
  rule      = aws_cloudwatch_event_rule.schedule[0].name
  target_id = "TriggerLambda"
  arn       = aws_lambda_function.api_processor.arn
}

resource "aws_lambda_permission" "allow_cloudwatch" {
  count         = var.enable_scheduled_execution ? 1 : 0
  statement_id  = "AllowExecutionFromCloudWatch"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api_processor.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.schedule[0].arn
}