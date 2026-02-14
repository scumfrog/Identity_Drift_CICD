# Evidence: H3 (Workflow Ref Binding)

Goal: same repo/event/ref, but different `job_workflow_ref` should flip STRICT verdict when the consumer pins allowed workflows.

## Consumer policy pin (used)

- `ALLOWED_WORKFLOWS=scumfrog/Identity_Drift_CICD/.github/workflows/01-push.yml@refs/heads/main`
- `ALLOWED_AUDIENCES=ci-oidc-lab`
- Consumer URL (tunnel): `https://polls-movement-uploaded-hosting.trycloudflare.com/introspect`

## Observed runs (GitHub Actions)

Date: 2026-02-14

- `01-push` (expected STRICT OK): run `22022405651`
- `05-alt` (expected STRICT FAIL by workflow_ref): run `22022405649`

## How to reproduce / download artifacts

```bash
unset GITHUB_TOKEN GH_TOKEN
gh run download -R scumfrog/Identity_Drift_CICD 22022405651
gh run download -R scumfrog/Identity_Drift_CICD 22022405649
```

Each run uploads an artifact with `result.json` and `context.json`.

