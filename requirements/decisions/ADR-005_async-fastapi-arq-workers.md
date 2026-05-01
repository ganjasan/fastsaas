---
tags: [decision, status/accepted, category/backend, priority/high]
created: 2026-05-01
decided: 2026-05-01
supersedes: []
traces_to:
 related:
 - "[[ADR-002_component-architecture]]"
 spike: platform-saas-core-architecture-spike
 epic: the SaaS-core epic
---

# ADR-005: Async-throughout FastAPI + arq workers

## Status
Accepted

## Context

`platform` is greenfield. We must commit to a synchronous or asynchronous FastAPI model before writing the first router, because mixing the two within one app is the documented FastAPI footgun (a sync handler running on the async event loop blocks all concurrent requests until it returns).

Two forces dominate:

1. **Future requirement: streaming model execution.** Epic [a downstream verticalisation epic](https://github.com/FASTSAAS/fastsaas/issues/2) (Orchestrator core) will spawn Docker model containers and stream their JSON-Lines stdout to the user in real time — minutes-long calls with progress events. Native async streaming via `StreamingResponse`/SSE is cheap; bolting it onto a sync app means a separate WebSocket sidecar.
2. **SaaS-core itself.** Most write-paths under epic [#16](https://github.com/FASTSAAS/fastsaas/issues/16) are short (< 100 ms). Some are IO-bound (OAuth callback, SMTP send, S3 upload) and benefit from async even before #2 lands.

Python 3.12 async tooling (`asyncio.TaskGroup`, modern `asyncio` semantics, `pytest-asyncio` maturity) has removed most of the historical pain of "async everywhere."

## Decision

**Asynchronous FastAPI throughout** the entire `platform` backend, with **arq** as the Redis-backed worker for jobs that exceed an in-request budget.

Concrete commitments:

- **Routes:** every handler is `async def`. Sync handlers are forbidden; PRs introducing one fail review.
- **DB driver:** `asyncpg` (native async). Combined with SQLAlchemy 2.x async API or SQLModel async session.
- **Migrations:** Alembic configured with the async engine.
- **Workers:** **arq** for background jobs (shares the asyncio loop and asyncpg pool). Workers run as a separate process from web (same image, different command).
- **Tests:** `pytest-asyncio` is the standard; every test function that touches IO is `async def`.
- **Sync escape hatch:** only `fastapi.concurrency.run_in_threadpool(...)` for proven CPU-bound code (rare). Document each occurrence.
- **Job-vs-inline rule of thumb:** > 500 ms or external IO with retry → arq job; otherwise inline with `await`.

## Alternatives Considered

### Sync FastAPI + RQ workers

- Simpler tests; familiar Django-style mental model.
- Streaming model-execution progress (epic #2) requires a separate WebSocket server or Redis-pubsub sidecar.
- DB driver becomes `psycopg` (sync); per-request thread pool overhead for IO.
- **Rejected:** the streaming requirement makes this a near-term refactor target; better to absorb async cost once at greenfield.

### Hybrid sync handlers + async only where streaming is needed

- Smallest async surface; only streaming endpoints are async.
- Mixed `def`/`async def` handlers in the same app are the canonical FastAPI footgun: sync handlers in async runtime block the loop.
- **Rejected:** convention drift over time degrades into the worst of both worlds.

### Async FastAPI + Celery

- Celery is the Python task-queue incumbent.
- Celery is sync-first; integration with async producers requires `aio-pika` or `aiogram` shims.
- arq is async-native and shares our connection pool; one fewer adapter.
- **Rejected:** arq fits cleanly; Celery's broader feature set is unused at our scale.

## Consequences

### Positive

- Streaming `StreamingResponse` and SSE work out of the box for the eventual model-execution UX.
- Single-driver DB story (asyncpg) avoids the dual-driver maze.
- arq workers reuse the same connection pool, shrinking ops complexity.
- AI-coding tools (Claude, Cursor) handle async FastAPI patterns well; `pytest-asyncio` is the documented norm.

### Negative

- All test functions become `async def`; mild boilerplate.
- Bugs from forgotten `await` are a real failure mode; mitigated by linting (`ruff` rule `RUF006`) and code review.
- Rare CPU-bound code (e.g., heavy CSV parsing) must be wrapped in `run_in_threadpool` or pushed to an arq worker.

## Open Questions

- Worker library for SaaS-core: locked to **arq**. May reconsider for the model-execution epic if requirements demand more fan-out semantics.
- User-initiated cancellation (e.g., abort a long calc): deferred to epic #2 streaming work.

## References

- [[../../openspec/changes/platform-saas-core-architecture-spike/design.md|Spike design.md — Decision #1]]
- [arq](https://arq-docs.helpmanual.io/) — async Redis-backed worker
- FastAPI async docs — https://fastapi.tiangolo.com/async/
