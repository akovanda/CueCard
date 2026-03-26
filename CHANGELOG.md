# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog (https://keepachangelog.com/en/1.0.0/),
and this project adheres to Semantic Versioning.

## [Unreleased]
### Added
- Dedicated worker process for queue ingestion and expired usage-boost cleanup
- Centralized settings with embedding-dimension validation against the database schema
- Lease/retry metadata for queued ingestion work
- `actionlint` workflow and Trivy gating for high/critical findings

### Changed
- Retrieval ranking now uses vector distance plus normalized vote and usage boosts
- API request validation and response models are explicit across retrieval, documents, logs, stats, and config
- Helm, Compose, and Kubernetes examples now keep `DATABASE_URL` in Secrets and enable API key auth by default
- README, deploy docs, RAG guide, and examples were rewritten to match the current runtime and CI flow

## [0.2.0] - 2025-11-02
### Added
- Complete RAG API endpoints: retrieve, record, documents, vote, log, stats, config
- Deterministic local embedding fallback
- Voting/boosting system (permanent + temporary boosts)
- Dockerized stack with Postgres + pgvector and Alembic migrations
- Helm chart and Kubernetes manifests
- Comprehensive pytest suite and examples

[Unreleased]: https://github.com/akovanda/CueCard/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/akovanda/CueCard/releases/tag/v0.2.0
