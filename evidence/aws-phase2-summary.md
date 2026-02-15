# Evidence: Phase 2 (AWS) OIDC Trust Policies

Goal: reproduce identity-drift outcomes in real IAM by comparing a LAX trust policy vs STRICT policies for GitHub Actions OIDC.

Repo: `scumfrog/Identity_Drift_CICD`

## AWS Resources (created via CLI)

- Account: `244477276723`
- Region used for lab: `eu-west-1`
- S3 bucket (dummy): `identity-drift-lab-244477276723-2154d781`
- OIDC provider:
  - ARN: `arn:aws:iam::244477276723:oidc-provider/token.actions.githubusercontent.com`
  - URL: `https://token.actions.githubusercontent.com`
  - ClientID: `sts.amazonaws.com`
  - Thumbprint: `6938fd4d98bab03faadb97b34396831e3780aea1`
- IAM role:
  - Name: `GitHubActionsIdentityDriftLabRole`
  - ARN: `arn:aws:iam::244477276723:role/GitHubActionsIdentityDriftLabRole`
- Role permission: inline `ListBucketPolicy` (`s3:ListBucket` on the bucket ARN)

## What “success” means

The workflow step **AWS proof** performs:

1. Requests a GitHub OIDC token with `audience=sts.amazonaws.com`
2. Calls `aws sts assume-role-with-web-identity` on `AWS_ROLE_ARN`
3. Calls `aws s3api list-objects-v2 --bucket $AWS_LAB_BUCKET --max-keys 5`

Success signal: STS assume succeeds and S3 returns JSON with `KeyCount` (bucket is empty, so usually `KeyCount: 0`).

Failure signal: STS returns `AccessDenied` ("Not authorized to perform sts:AssumeRoleWithWebIdentity").

## Trust Policies (in repo)

Baseline (LAX):
- `aws/trust-lax-final.json`
- Allows: `sub` wildcard for the repo (StringLike on `repo:scumfrog/Identity_Drift_CICD:*`)

STRICT v1 (ref pin):
- `aws/trust-strict-v1-final.json`
- Pins:
  - `aud == sts.amazonaws.com`
  - `sub == repo:scumfrog/Identity_Drift_CICD:ref:refs/heads/main`

STRICT v2 (ref + workflow pin):
- `aws/trust-strict-v2-final.json`
- Pins:
  - `aud == sts.amazonaws.com`
  - `sub == repo:scumfrog/Identity_Drift_CICD:ref:refs/heads/main`
  - `job_workflow_ref == scumfrog/Identity_Drift_CICD/.github/workflows/01-push.yml@refs/heads/main`

STRICT v3 (attempted event pin):
- `aws/trust-strict-v3-final.json`
- Adds:
  - `event_name == push`
- Observed: this broke even `01-push` (STS `AccessDenied`), so we reverted to v2.

## Evidence Runs (GitHub Actions)

Note: run IDs are immutable references for reproducibility; download artifacts/logs for the specific run.

### LAX baseline (ambient authority visible)

- `02-pr` (PR context) **OK**: run `22033411317`
  - AWS proof succeeded (assume role + list bucket) under LAX trust.

### STRICT v1 / v2 (drift blocked)

Push on `main` via `01-push`:
- **OK** (assume + list): run `22033591718`
- **OK** (assume + list): run `22033604517`

Workflow substitution on `main` via `05-alt` (same ref, different workflow):
- **DENIED** (STS AccessDenied): run `22033604526`

PR context via `02-pr`:
- **DENIED** (STS AccessDenied): run `22033644786`

## How to view logs / reproduce (no token exposure)

List runs:

```bash
unset GITHUB_TOKEN GH_TOKEN
gh run list -R scumfrog/Identity_Drift_CICD --limit 20
```

View a specific run log:

```bash
unset GITHUB_TOKEN GH_TOKEN
gh run view -R scumfrog/Identity_Drift_CICD <RUN_ID> --log
```

Download artifacts:

```bash
unset GITHUB_TOKEN GH_TOKEN
gh run download -R scumfrog/Identity_Drift_CICD <RUN_ID>
```

Check current role trust policy (AWS):

```bash
aws --profile identity-drift-lab-admin iam get-role \
  --role-name GitHubActionsIdentityDriftLabRole \
  --query 'Role.AssumeRolePolicyDocument' --output json
```

