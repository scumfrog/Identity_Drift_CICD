# Identity Drift CI/CD Lab (GitHub Actions OIDC)

Reproducible lab to measure and demonstrate *identity binding* failures in CI/CD (identity drift / token confusion) using real GitHub Actions OIDC tokens. The goal is not to “weaponize”, but to show which invariants are broken by lax validation.

## What It Demonstrates

- A token can be cryptographically valid and still be unsafe out of context: signature verification proves authenticity, not intent.
- `job_workflow_ref` is a control-plane boundary (H3): it prevents workflow substitution within the same repo.
- `aud` is purpose binding (H4): it prevents valid tokens from being reusable capabilities across consumers.

Recommended minimal invariant set for consumers: `iss`, `aud`, `repository`, `event_name`, `ref`, `job_workflow_ref` (+ `environment` when used).

## Layout (Core)

- `app/consumer.py`: FastAPI consumer (`/introspect`, `/policies`, `/health`)
- `app/policies.py`: LAX vs STRICT policies (env vars)
- `scripts/decode_and_diff.py`: local diff helper for `result.json`
- Workflows:
  - `.github/workflows/01-push.yml`
  - `.github/workflows/02-pr.yml`
  - `.github/workflows/05-alt.yml`
  - `.github/workflows/03-dispatch.yml` (kept for H4)
- AWS trust policies (versioned):
  - `aws/trust-lax-final.json`
  - `aws/trust-strict-v1-final.json`
  - `aws/trust-strict-v2-final.json`

## Consumer (Local)

```bash
cd app
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn consumer:app --host 0.0.0.0 --port 8081
```

GitHub Actions calls `secrets.CONSUMER_URL`:
- if it is `https://<host>`, the workflow appends `/introspect`
- if it is `https://<host>/introspect`, it is used as-is

## Hypotheses (Publishable)

**H3 — Workflow Ref Binding**
If the consumer does not pin `job_workflow_ref`, any workflow in the repository with `id-token: write` can mint “equivalent” tokens, collapsing the control-plane into ambient authority.

**H4 — Audience Binding (Purpose Binding)**
If the consumer does not enforce `aud`, a valid token can be accepted outside its intended purpose, turning into a reusable capability across consumers.

## Experiments (Phase 1: Self-Hosted Consumer)

### H3: Workflow Ref Binding

Consumer configuration (pin to `01-push` only):

```bash
ALLOWED_WORKFLOWS="scumfrog/Identity_Drift_CICD/.github/workflows/01-push.yml@refs/heads/main" \
ALLOWED_AUDIENCES="ci-oidc-lab" \
uvicorn consumer:app --host 0.0.0.0 --port 8081
```

Trigger: push to `main` (runs `01-push` and `05-alt`).

### H4: Audience Binding (Single Knob)

Consumer configuration (pin to `03-dispatch`):

```bash
ALLOWED_WORKFLOWS="scumfrog/Identity_Drift_CICD/.github/workflows/03-dispatch.yml@refs/heads/main" \
ALLOWED_AUDIENCES="ci-oidc-lab" \
uvicorn consumer:app --host 0.0.0.0 --port 8081
```

Trigger (two runs, same workflow, different audience):

```bash
unset GITHUB_TOKEN GH_TOKEN
gh workflow run -R scumfrog/Identity_Drift_CICD "03-dispatch" -f audience=ci-oidc-lab
gh workflow run -R scumfrog/Identity_Drift_CICD "03-dispatch" -f audience=other-service
```

## AWS (Phase 2: Real IAM)

Goal: reproduce the same pattern in IAM (LAX vs STRICT) using GitHub OIDC -> STS.

Trust policies:
- LAX: `aws/trust-lax-final.json` (repo wildcard)
- STRICT v1: `aws/trust-strict-v1-final.json` (pin `aud` + `sub` to `refs/heads/main`)
- STRICT v2: `aws/trust-strict-v2-final.json` (v1 + pin `job_workflow_ref` to `01-push`)

Note: a STRICT v3 with `event_name == push` was tested and broke even `01-push` (STS AccessDenied), so it is not kept in this repo.

## Evidence (Run IDs)

### Phase 1 (Consumer)

H3 (push/main, workflow pin):
- `01-push` STRICT OK: run `22022405651`
- `05-alt` STRICT FAIL (workflow_ref): run `22022405649`

H4 (same workflow/ref/event, only `aud` changes):
- `03-dispatch` (`audience=ci-oidc-lab`) STRICT OK: run `22022467100`
- `03-dispatch` (`audience=other-service`) STRICT FAIL (`aud_not_allowed`): run `22022467170`

### Phase 2 (AWS IAM, STRICT v2)

- push/main `01-push` OK (AssumeRoleWithWebIdentity + ListBucket): run `22033604517`
- push/main `05-alt` DENIED (STS AccessDenied): run `22033604526`
- PR `02-pr` DENIED (STS AccessDenied): run `22033644786`

View logs / artifacts:

```bash
unset GITHUB_TOKEN GH_TOKEN
gh run view -R scumfrog/Identity_Drift_CICD <RUN_ID> --log
gh run download -R scumfrog/Identity_Drift_CICD <RUN_ID>
```

## Local Diffs (Claims / Context)

```bash
python3 scripts/decode_and_diff.py <A.json> <B.json>
```
