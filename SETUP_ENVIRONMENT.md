# Setting Up GitHub Environment Protection

After pushing this commit, you need to configure the `production` environment in GitHub:

## Steps:

1. Go to your repository on GitHub:
   https://github.com/cvtreharne-cvt/fortaleza-purchase-agent

2. Click **Settings** (top right)

3. In the left sidebar, click **Environments**

4. Click **New environment** (or select `production` if it exists)

5. Name it: `production`

6. Under **Deployment protection rules**:
   - ✅ Check **Required reviewers**
   - Add yourself as a reviewer
   - (Optional) Set **Wait timer** for an additional delay

7. Click **Save protection rules**

## What This Does:

- When GitHub Actions reaches the `deploy` job, it will **pause**
- You'll get a notification to approve the deployment
- You review the Terraform plan in the logs
- You click **Approve and deploy** or **Reject**
- Only after approval does Terraform run

## First Run After Push:

The workflow will fail at the deploy step with a message like:
"Environment protection rules not configured"

This is expected - you need to set up the environment first (steps above).

Then re-run the workflow or push another commit.
