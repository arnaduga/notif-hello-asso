# API Processor Lambda with Terraform/OpenTofu

This project extracts payements inforamtion form Hello Asso API, and prepare a synthesis CSV file, send the link via SNS Email:

1. Retrieves API credentials from AWS Parameter Store
2. Calls an external API using those credentials
3. Processes the API response data
4. Generates a CSV file with the processed data
5. Stores the file in S3
6. Generated a Presigned URL
7. Send a SNS notification with the appropriate URL


## Architecture

The solution consists of the following AWS resources:
- Lambda function with Python 3.11 runtime
- IAM role with permissions for Parameter Store, S3, SNS, and CloudWatch Logs
- SNS topic for notifications with processed data
- Parameter Store parameters for API URL, API Client ID, API Client Secret
- S3 with a document lifecycle to keep the files 2 years
- CloudWatch Log Group for Lambda logs
- CloudWatch Event Rule for scheduled execution

## Setup Instructions

1. Clone this repository:
   ```
   $ git clone <repository-url>
   $ cd <repository-directory>
   ```

2. Create a `terraform.tfvars` file with your configuration:
   ```
   $ cp terraform.tfvars.template terraform.tfvars
   ```
   
3. Edit the `terraform.tfvars` file with your specific values:
   ```hcl
   # HELLO ASSO Settings
   api_url       = "https://api.helloasso.com/v5/organizations/<organization_slug>/payments"
   api_url_token = "https://api.helloasso.com/oauth2/token"

   ## HELLO ASSO AuthN
   api_client_id     = "abc" # This is sensitive, keep it secure!
   api_client_secret = "abc" # This is sensitive, keep it secure!


   # Project
   environment    = "dev"
   project_prefix = "helloasso-payments"
   random_number  = "627364019283" # Random

   notification_email = "arnaduga@example.com"

   enable_scheduled_execution = true                # Set to true to enable the CloudWatch schedule
   schedule_expression        = "cron(0 6 1 * ? *)" # Monthly, at 6am UTC
   ```


3. Prepare the modules for the Pyhton script:
   ```
   $ cd lambda
   $ pip install -r requirements.txt -t modules
   ```

4. Initialize Terraform:
   ```
   $ terraform init
   ```

5. Plan the deployment:
   ```
   terraform plan -var-file terrafor.tfvars
   ```

6. Apply the configuration:
   ```
   terraform apply -var-file terrafor.tfvars
   ```
   
7. Confirm the deployment by checking the outputs:
   ```
   terraform output
   ```

8. In your mailbox, confirm you want to receive SNS notifications emails.

## Security Considerations

- The API credentials are stored as a SecureString in Parameter Store
- IAM permissions follow the principle of least privilege
- Lambda has only the permissions it needs to function
