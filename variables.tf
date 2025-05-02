variable "aws_region" {
  description = "The AWS region to deploy resources"
  type        = string
  default     = "eu-west-1"
}

variable "environment" {
  description = "Environment name (e.g., dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "project_prefix" {
  description = "Prefix for project resources"
  type        = string
  default     = "myAsso-helloasso"
}

variable "project_context" {
  description = "A quick clue on the project context"
  type        = string
  default     = ""
}

variable "random_number" {
  description = "Random number for unique resource names"
  type        = string
}

variable "api_url" {
  description = "URL of the API to call"
  type        = string
  # No default - should be provided
}

variable "api_url_token" {
  description = "URL of the API TOKEN to call"
  type        = string
  # No default - should be provided
}

variable "api_client_id" {
  description = "API Client_id for authentication"
  type        = string
  sensitive   = true
  # No default - should be provided
}

variable "api_client_secret" {
  description = "API Client_secret for authentication"
  type        = string
  sensitive   = true
  # No default - should be provided
}

variable "enable_scheduled_execution" {
  description = "Whether to enable scheduled execution of the Lambda function"
  type        = bool
  default     = false
}

variable "schedule_expression" {
  description = "CloudWatch Events schedule expression for Lambda execution"
  type        = string
  default     = "rate(1 day)"
}

variable "notification_emails" {
  description = "List of emails address to receive SNS notifications with the presigned URL (optional)"
  type        = list(string)
  default     = []
}

variable "presigned_url_expiration_seconds" {
  description = "Expiration time in seconds for the S3 presigned URL"
  type        = number
  default     = 172800
}