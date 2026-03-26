# Contributing to CueCard

Thanks for your interest in contributing! We welcome issues, ideas, docs, and code.

## Quick links
- Security policy: SECURITY.md
- Code of Conduct: CODE_OF_CONDUCT.md
- How to run tests: see below

## Development setup

Prerequisites:
- Docker and Docker Compose
- Python 3.11+ (optional, for running examples locally)

Bring the stack up:

```bash
cp .env.example .env
docker compose up -d --build
```

The sample `.env.example` enables API key auth with `X-API-Key: change-me`. Rotate that value or override it in `.env` before sharing the service outside your machine.

Run migrations explicitly when you need a clean DB:

```bash
docker compose run --rm migrations
```

Run tests (inside containers):

```bash
docker compose run --rm --no-deps -e COVERAGE_FILE=/tmp/.coverage api pytest -v
```

CI writes coverage output to `.artifacts/coverage.xml` so local and CI test runs do not dirty tracked files.

Useful commands:
- Rebuild the API image: `docker compose build api`
- View logs: `docker compose logs -f api`
- Run Alembic migrations: `docker compose run --rm migrations`

## Pull requests
- Create a feature branch from `main`.
- Keep PRs focused and small; include tests when changing behavior.
- Update docs if user-visible behavior or config changes.
- Ensure `docker compose run --rm --no-deps -e COVERAGE_FILE=/tmp/.coverage api pytest -v` passes.

## Commit style
Use clear, descriptive commits. Example prefixes: feat, fix, docs, chore, test, refactor.

## Coding guidelines
- Python: follow PEP 8 where practical; type hints encouraged.
- Avoid breaking public APIs without discussion.

## Issue triage
When filing an issue, include:
- What you did, expected, and observed
- Repro steps (commands, payloads)
- Logs (redact secrets)
- Environment (OS, Docker, commit/tag)

## Releasing
Pushes to `main` trigger `.github/workflows/release.yml`, which creates the next patch tag `vX.Y.Z`, publishes `ghcr.io/<owner>/cuecard:X.Y.Z` and `:latest`, and creates a GitHub Release. Use `workflow_dispatch` on the same workflow if you need to rerun a release manually.

If the image push fails with `403 Forbidden` from `ghcr.io`, the package usually exists without this repository having workflow access. Fix that in the package's GitHub settings under `Actions access`, or set `GHCR_TOKEN` and `GHCR_USERNAME` secrets so releases publish with a dedicated package token.
