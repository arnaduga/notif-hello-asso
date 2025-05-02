# AWS Payements Extractor for Hello Asso

## Introduction

### The "Why"

Hello Asso is a wonderful solution for French association to collect money, for subscription, payment for items, etc.

But the access to the information of the Hello Asso is "full or nothing": hard to give an access to the accounting team to only the payements received.

That is why I decided to develop a small thing to automate the data extraction on a regular basis.

### The "How"

On AWS, this project builds a set of compenents:
- A Lambda function, the core of the system
- Some items in SSM Parameter Store: just a way to store some secrets, like credentials
- An S3 Bucket, to store all the extraction file (once by month, during 2 years)
- An SNS topic, with one email notification (optional), to get the URL to the extracted file

The core Lambda function is using the [Hello Asso API](https://dev.helloasso.com/reference) to make a call to `/payments` API endpoint.

Then, the retrieve infomation if parsed, and reformated (with translation from technical statuses, for instance, to French sentences).

The generated CSV file is then stored into S3 bucket and an SNS message is pushed, including a URL (presigned).

That's all


## Setup Instructions

1. Clone this repository:
   ```
   $ git clone https://github.com/arnaduga/notif-hello-asso
   $ cd notif-hello-asso
   ```

2. Create a `terraform.tfvars` file for your configuration:
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
   environment     = "dev"
   project_prefix  = "helloasso-payments"
   project_context = "mwa"
   random_number   = "627364019283" # Random

   notification_emails = ["arnaduga@example.com"]

   enable_scheduled_execution = true                # Set to true to enable the CloudWatch schedule
   schedule_expression        = "cron(0 6 1 * ? *)" # Monthly, at 6am UTC
   ```

   In the `api_url`, replace the `<organization_slug>` by your organization slug: you can locate it in the dashboard URL : `https://admin.helloasso.com/<yourSLUGisHERE>/accueil`

   The `api_client_id` and `api_client_secret` can be found in the Integration and API page, located here: `https://admin.helloasso.com/<yourSLUGhere>/integrations`

   The `environment`is just a way to distinguish mmultiple deployment. It impacts some resource names and tags.

   The `project_prefix` is mainly for naming: it helps to better identify resources
   The `project_context` is for tagging: helps to identify costs

   The `random_number` is a random number (or event text by the way) used to generate a UNIQUE S3 bucket name.

   The `notification_email` is used to set a subscription to the SNS Topic. Just after applying this config, remind to VALIDATE the subscribtion thanks to the link received by email.


   The last 2 variables are optional and use if you want the Lmabda function to be scheduled on a regular basis, following the cron syntax.


3. Prepare the modules for the Pyhton script:

   The Lambda function works with some dependancies. Prior to apply the Terraform, you have to prepare the modules.

   However, no need to `venv` or to instal them globally, use this syntax to put the deps into `modules` subfolder: the Python script is expecting it.

   ```
   $ cd lambda
   $ pip install -r requirements.txt -t modules
   ```

4. Classical Terraform apply
   ```
   $ terraform init
   $ terraform plan -var-file terrafor.tfvars
   $ terraform apply -var-file terrafor.tfvars
   ```
   

## Security Considerations

- The API credentials are stored as a SecureString in Parameter Store
- IAM permissions follow the principle of least privilege
- Lambda has only the permissions it needs to function
