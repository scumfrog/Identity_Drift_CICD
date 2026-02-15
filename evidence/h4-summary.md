# Evidence: H4 (Audience Binding / Purpose Binding)

Goal: keep `job_workflow_ref`, `event_name`, `ref` constant and change only `aud` to show STRICT flips solely due to audience enforcement.

## Consumer policy pin (used)

- `ALLOWED_WORKFLOWS=scumfrog/Identity_Drift_CICD/.github/workflows/03-dispatch.yml@refs/heads/main`
- `ALLOWED_AUDIENCES=ci-oidc-lab`
- Consumer URL (tunnel): `https://polls-movement-uploaded-hosting.trycloudflare.com/introspect`

## Observed runs (GitHub Actions)

Date: 2026-02-14

Two runs of the same workflow (`03-dispatch`) differing only by input `audience`:

- `audience=ci-oidc-lab` (expected STRICT OK): run `22022467100`
- `audience=other-service` (expected STRICT FAIL by `aud_not_allowed`): run `22022467170`

## How to reproduce

```bash
unset GITHUB_TOKEN GH_TOKEN
gh workflow run -R scumfrog/Identity_Drift_CICD "03-dispatch" -f audience=ci-oidc-lab
gh workflow run -R scumfrog/Identity_Drift_CICD "03-dispatch" -f audience=other-service
```

## How to download artifacts

```bash
unset GITHUB_TOKEN GH_TOKEN
gh run download -R scumfrog/Identity_Drift_CICD 22022467100
gh run download -R scumfrog/Identity_Drift_CICD 22022467170
```

Each run uploads an artifact with `result.json` and `context.json`.

