
# CueCard Deploy Kit (v0.2)

This kit lets you ship CueCard as a sidecar/companion next to any service via **Docker Compose** or **Helm**, and optionally publish images to **GHCR** and **Docker Hub**.

## Images
- `ghcr.io/<your-org>/cuecard:0.2` and `:latest`
- (optional) `docker.io/<your-user>/cuecard:0.2`

> Uses the Dockerfile already in your repo (`api/Dockerfile`).

---

## A) GitHub Actions: build + push (GHCR & optional Docker Hub)

Place the workflow from `.github/workflows/publish.yml` in your repo and push a **tag** (e.g., `v0.2`).

### Required repo settings
- **Actions → General → Workflow permissions:** enable "Read and write permissions".
- For Docker Hub (optional): create secrets `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN`.

The workflow will build multi-platform images (`linux/amd64, linux/arm64`) and push:
- `ghcr.io/<OWNER>/cuecard:<tag>` and `:latest`
- optionally `docker.io/<USER>/cuecard:<tag>` and `:latest`

---

## B) Helm (Kubernetes)

### Install
```bash
helm upgrade --install cuecard ./helm/cuecard   --set image.repository=ghcr.io/<your-org>/cuecard   --set image.tag=0.2   --set env.EMBEDDING_PROVIDER=openai   --set secretEnv.OPENAI_API_KEY=<your-key>   --namespace your-ns --create-namespace
```

### Sidecar pattern
Add a second container to your app's Deployment. Example patch (conceptual):

```yaml
containers:
  - name: your-app
    # ...
  - name: cuecard
    image: ghcr.io/<your-org>/cuecard:0.2
    envFrom:
      - configMapRef: { name: cuecard }
      - secretRef: { name: cuecard-secret }
    ports: [{containerPort: 8000}]
```

The provided chart deploys CueCard standalone. If you want it as a sidecar, copy the container block into your app chart or use a Helm subchart.

---

## C) Docker Compose (sidecar)

Use `compose/compose.cuecard.example.yml` alongside your service compose file:

```bash
docker compose -f docker-compose.yml -f compose/compose.cuecard.example.yml up -d
```

Your app can call `http://cuecard:8000` over the default network.

---

## Configuration

Key env vars (see chart `values.yaml` for full list):

- `EMBEDDING_PROVIDER`: `openai` or `local` (default `local` for zero-keys)
- `OPENAI_API_KEY`: required if `EMBEDDING_PROVIDER=openai`
- `EMBEDDING_MODEL`: default `text-embedding-3-small` (1536-dim)
- `EMBEDDING_DIM`: default `1536`
- `DATABASE_URL`: e.g., `postgresql+psycopg://ctx:ctxpw@db:5432/ctx`
- `RERANK_WEIGHT`: default `0.1` (gentle success-rate boost)
- `RETRIEVAL_OVERFETCH`: default `8`
- `WORKER_POLL_SEC`: default `2`
- `WORKER_BATCH`: default `32`

Probes are enabled; resources can be tuned in `values.yaml`.

---

## Security

If exposing beyond your cluster/VPC, add an auth header:
- Set `security.apiKeyHeaderName` in Helm values (default `X-API-Key`).
- Put your key in `secretEnv.CUECARD_API_KEY`.
- The server will reject requests missing or mismatched keys.

---

## Smoke test

Once running:
```bash
curl -s http://<host>:<port>/health

# queue an item
curl -s http://<host>:<port>/record -H "Content-Type: application/json" -d '{
  "items": [{
    "source":"email","op_key":"email.reply","title":"Test",
    "content":"hello world","tags":["smoke"]
  }]
}'

# retrieve after ~2s
curl -s http://<host>:<port>/retrieve -H "Content-Type: application/json" -d '{"goal":"reply politely","k":3}'
```
