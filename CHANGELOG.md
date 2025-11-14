# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog (https://keepachangelog.com/en/1.0.0/),
and this project adheres to Semantic Versioning.

## [Unreleased]
### Added
- New `GET /logs` endpoint to query raw tool logs by time range and filters (op_key, doc_id, status range, pagination)
- Alembic migration `0004_tool_log_timestamp` adding `created_at` column and index to `tool_log`
- `examples/chat_history_example.py` demonstrating session timelines with `/logs`
- Documentation updates in `README.md`, `examples/README.md`, and `RAG-GUIDE.md` for session logging and chat history

## [0.2.0] - 2025-11-02
### Added
- Complete RAG API endpoints: retrieve, record, documents, vote, log, stats, config
- Deterministic local embedding fallback
- Voting/boosting system (permanent + temporary boosts)
- Dockerized stack with Postgres + pgvector and Alembic migrations
- Helm chart and Kubernetes manifests
- Comprehensive pytest suite and examples

[Unreleased]: https://github.com/OWNER/REPO/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/OWNER/REPO/releases/tag/v0.2.0
MIT License

Copyright (c) 2025 CueCard contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
