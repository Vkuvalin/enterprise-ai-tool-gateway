# enterprise-ai-tool-gateway

Backend-first MVP for a controlled enterprise AI tool gateway.

The current local/demo surface exposes a FastAPI adapter over deterministic
access, procurement and maintenance-lite workflows plus an independent
React/Vite local web client under `frontend/`. It is not production-ready, does
not implement auth/RBAC/tenant isolation, and does not call real enterprise
systems by default.

## Local API

```bash
uv run uvicorn enterprise_ai_tool_gateway.api.http.app:app --reload
```

Stage 8 endpoints are versioned under `/api/v1`.

## Local Frontend

```bash
cd frontend
npm install
npm run dev
```

The Vite dev server proxies `/api` to `http://localhost:8000/api`. The frontend
API client uses `/api/v1` by default and is isolated under `frontend/src/api/`.

Frontend build/typecheck:

```bash
cd frontend
npm run typecheck
npm run build
```

## Validation

```bash
uv run pytest
uv run ruff check .
uv run pyright
git diff --check
uv run python scripts/run_eval.py
uv run python scripts/run_eval.py --format json
cd frontend
npm install
npm run typecheck
npm run build
```
