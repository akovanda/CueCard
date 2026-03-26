# CueCard Deploy Kit

This guide covers the supported deployment surfaces for CueCard:
- GitHub Actions publishing to GHCR
- Helm for Kubernetes
- Docker Compose sidecar deployment
- Static Kubernetes manifests for a simple starting point

## Images
- `ghcr.io/<your-org>/cuecard:<release-version>` and `:latest`

> Uses the Dockerfile already in your repo (`api/Dockerfile`).

## A) GitHub Actions: build + push to GHCR

Use `.github/workflows/release.yml`. Every push to `main` computes the next patch release, creates a GitHub Release tag (`vX.Y.Z`), and publishes:
- `ghcr.io/<OWNER>/cuecard:X.Y.Z`
- `ghcr.io/<OWNER>/cuecard:latest`

### Required repo settings
- **Actions → General → Workflow permissions:** enable "Read and write permissions".
- **Packages:** allow GitHub Actions to write to GHCR for this repository.

## B) Helm (Kubernetes)

### Install
```bash
cat > cuecard-values.yaml <<'EOF'
image:
  repository: ghcr.io/<your-org>/cuecard
  tag: "<release-version>"
env:
  EMBEDDING_PROVIDER: openai
secretEnv:
  DATABASE_URL: postgresql+psycopg://ctx:ctx@postgres:5432/ctx
  OPENAI_API_KEY: <your-openai-key>
  CUECARD_API_KEY: <long-random-api-key>
EOF

helm upgrade --install cuecard ./helm/cuecard \
  --namespace your-ns \
  --create-namespace \
  -f cuecard-values.yaml
```

The chart renders:
- a pre-install/pre-upgrade migrations Job
- an API Deployment and Service
- a worker Deployment

### Sidecar pattern
Add a second container to your app's Deployment. Example patch (conceptual):

```yaml
containers:
  - name: your-app
    # ...
  - name: cuecard
    image: ghcr.io/<your-org>/cuecard:<release-version>
    envFrom:
      - configMapRef: { name: cuecard }
      - secretRef: { name: cuecard-secret }
    ports: [{containerPort: 8000}]
```

The provided chart deploys CueCard as three pieces: a migration Job, an API Deployment, and a worker Deployment. If you want it as a sidecar, copy the API container block into your app chart and keep the worker as a separate Deployment.

## C) Docker Compose (sidecar)

Use `compose/compose.cuecard.example.yml` alongside your service compose file:

```bash
docker compose -f docker-compose.yml -f compose/compose.cuecard.example.yml up -d
```

Your app can call `http://cuecard-api:8000` over the default network, while `cuecard-worker` processes the ingestion queue.

## D) Static Kubernetes manifest

For small environments or as a starting point for another chart, use [deployment.yaml](k8s-manifests/deployment.yaml). It mirrors the secure defaults from Helm: secrets in `Secret`, non-root containers, `RuntimeDefault` seccomp, and no mounted service-account token.

## Configuration
Key settings (see [values.yaml](helm/cuecard/values.yaml) for the full chart surface):

- `EMBEDDING_PROVIDER`: `openai` or `local` (default `local` for zero-keys)
- `OPENAI_API_KEY`: required if `EMBEDDING_PROVIDER=openai`
- `EMBEDDING_MODEL`: default `text-embedding-3-small` (embedding dimension is derived from the model and must match the DB schema)
- `secretEnv.DATABASE_URL`: e.g., `postgresql+psycopg://ctx:ctx@db:5432/ctx`
- `secretEnv.CUECARD_API_KEY`: required for the chart and example manifests
- `image.tag`: defaults to `latest`; pin this to a concrete release in production
- `RERANK_WEIGHT`: default `0.1` (gentle success-rate boost)
- `RETRIEVAL_OVERFETCH`: default `8`
- `WORKER_POLL_SEC`: default `2`
- `WORKER_BATCH`: default `32`
- `WORKER_LEASE_SEC`: default `300`

Probes are enabled; resources can be tuned in `values.yaml`.

## Security

The chart and sample manifests enable API key auth by default:
- Set `security.apiKeyHeaderName` in Helm values if you need a custom header name.
- Put your key in `secretEnv.CUECARD_API_KEY`.
- Keep `DATABASE_URL`, `OPENAI_API_KEY`, and `CUECARD_API_KEY` in a values file or Secret workflow, not on the Helm CLI.
- The server rejects requests missing or mismatched keys.

## Smoke test

Once running:
```bash
curl -s http://<host>:<port>/health

# queue an item
curl -s http://<host>:<port>/record -H "X-API-Key: <your cuecard api key>" -H "Content-Type: application/json" -d '{
  "items": [{
    "source":"email","op_key":"email.reply","title":"Test",
    "content":"hello world","tags":["smoke"]
  }]
}'

# retrieve after the worker has processed the queue
curl -s http://<host>:<port>/retrieve -H "X-API-Key: <your cuecard api key>" -H "Content-Type: application/json" -d '{"goal":"reply politely","k":3}'

# log usage and query raw logs (optional)
curl -s -X POST http://<host>:<port>/log -H "X-API-Key: <your cuecard api key>" -H "Content-Type: application/json" -d '{"op_key":"smoke::session","status":200,"latency_ms":50}'
START=$(date -u -v-5M '+%Y-%m-%dT%H:%M:%SZ') ; END=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
curl -s "http://<host>:<port>/logs?op_key=smoke::session&start_time=$START&end_time=$END&limit=10" -H "X-API-Key: <your cuecard api key>" | jq
```

> Note: Run migrations before starting the API and worker so the queue lease columns and log timestamps are available.
