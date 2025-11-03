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

Run tests (inside containers):

```bash
docker compose exec api pytest -v
```

Useful commands:
- Rebuild the API image: `docker compose build api`
- View logs: `docker compose logs -f api`
- Run Alembic migrations: `docker compose run --rm migrations alembic upgrade head`

## Pull requests
- Create a feature branch from `main`.
- Keep PRs focused and small; include tests when changing behavior.
- Update docs if user-visible behavior or config changes.
- Ensure `docker compose exec api pytest -v` passes.

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
We tag releases as `vX.Y.Z`. Images are published via GitHub Actions to GHCR on tag push.

