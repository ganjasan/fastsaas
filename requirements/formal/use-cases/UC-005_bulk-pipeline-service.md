---
id: UC-005
title: Внешний bulk-pipeline сервис обрабатывает множество объектов через FASTSAAS API
level: Цель пользователя
priority: high
status: draft
created: 2026-05-01
author: Artem Konuchov (с Claude Code)
traces_to:
 related_features:
 - FE-CORE-1 # Actor-Centric (нужен AGENT/SERVICE actor type)
 - FE-CORE-3 # Audit с intent_hash для bulk grouping
 related_ar:
 - AR-3 # Orchestrator (bulk model executions)
 related_adr:
 - ADR-008 # Auth (API keys)
 - ADR-009 # Actor model
 - ADR-010 # Audit
 related_stakeholders:
 - Globex # Crypto-style bulk processing
 related_epic: the SaaS-core epic # Foundation; full bulk in dedicated epic
---

# UC-005: Внешний bulk-pipeline сервис обрабатывает множество объектов через FASTSAAS API

**Уровень:** Цель пользователя
**Приоритет:** Высокий (для Globex-style клиентов)
**Акторы:**
- **Org Admin** (HUMAN, setup phase)
- **Bulk Pipeline Service** (AGENT/SERVICE actor — см. UC-007 для решения, какой type)

**Связанные требования:** FE-CORE-1, FE-CORE-3

---

## Краткое описание

Крупная организация (например, Globex Asset Management) имеет nightly automated pipeline: cron-job в 02:00 CET → читает список из 50-200 объектов из внешней системы (например, GIF / SAP) → для каждой entity выполняет последовательность через FASTSAAS API: read project, run AnalysisPipeline-A, store result, generate export. Это сервисный workflow — не interactive, без HUMAN сидящего за клавиатурой. Service authenticates через API key, имеет ограниченный scope, все его действия в `audit_log` группируются одним `intent_hash` для одного pipeline-run'а.

## Предусловия

- Org Admin создал service-account (`actor_type=SERVICE`, или AGENT с designated parent — см. UC-007).
- Service имеет API key + scope set: `read:project`, `write:project`, `run:model` в рамках конкретного department.
- Внешняя система (cron / Airflow / GitLab CI / etc.) хранит API key в secret manager и umеет его использовать.
- FASTSAAS MCP / REST API доступен (production endpoint).

## Постусловия (успех)

- Все объекты из batch обработаны (или partial failure явно зафиксирован).
- Каждое действие в `audit_log` помечено: `actor_id=service`, `intent_hash=<bulk-run-id>`, `intent_metadata.batch_id=<external_id>`, `intent_metadata.batch_position=N/M`.
- Org Admin может в UI открыть «Recent batch runs» и увидеть detailed trail.
- Аналитика: aggregated metrics (объекты processed, success rate, total runtime) доступны в Org reports.

## Постусловия (неудача)

- Если pipeline превысил quota — operations rejected с 429; pipeline должен retry.
- Если service token revoked — все in-flight operations rejected; pipeline уведомляет owner.
- Partial failure: успешные actions committed, failed — audit-row с `action_failed=true` + reason.

---

## Основной поток (Pipeline Run)

| # | Актор (Pipeline Service) | Система |
|---|--------------------------|---------|
| 1 | Cron-job стартует в 02:00; читает list of 50 entities from internal SAP | |
| 2 | Generates `intent_hash = bulk:<uuid7>`; помещает в headers `X-FASTSAAS-Intent-Hash` для всех subsequent calls | |
| 3 | (Loop, для каждого property) | |
| 4 | Calls `POST /api/projects` with project data, dept_id=Asset_Management | |
| 5 | | Capability check: `write:project` в Asset Management — OK; создаёт project; audit с указанным intent_hash + `batch_position=N/50` |
| 6 | Calls `POST /api/projects/{id}/run` with model=analysis-pipeline-b | |
| 7 | | Capability `run:model` — OK; spawns model container; returns 202 + execution_id |
| 8 | (Async) Polls `/api/executions/{id}` до status=done | |
| 9 | | Возвращает результат + результирующий output_blob_id |
| 10 | Calls `GET /api/exports?project={id}&format=xlsx` | |
| 11 | | Capability `read:project` + `read:result` — OK; rendered file URL returned |
| 12 | Pipeline сохраняет URL в external system | |
| 13 | (End loop) После 50 entities — финальный summary call | |
| 14 | | Может быть кастомный endpoint типа `POST /api/batches/{intent_hash}/finalize` который пишет summary audit row |
| 15 | Pipeline отправляет email summary owner через external SMTP | |

---

## Альтернативные потоки

### [A1] Setup — Org Admin создаёт service account

| # | Актор (Org Admin) | Система |
|---|-------------------|---------|
| 1 | Settings → Service Accounts → Create New | |
| 2 | | Form: name, description, dept assignment, scope set (read/write/run on which resources) |
| 3 | Указывает: name="Nightly Asset Pipeline", dept=Asset Management, scopes=[read:project, write:project, run:model:analysis-pipeline-b] | |
| 4 | | Создаёт actor (`actor_type=SERVICE` per UC-007 решение); generates API key (показан один раз, можно скопировать) |
| 5 | Org Admin копирует API key в external secret manager | |
| 6 | | Service ready for use; audit «service_created» |

### [A2] Partial failure — pipeline обрабатывает recovery

- На шаге 6 для object #23: model container fails (e.g., invalid input).
- FASTSAAS возвращает 422 + structured error.
- Pipeline решает: continue с object #24 (skip failed) vs abort all.
- Все failures логируются в `audit_log` с `action_failed=true` + `failure_reason`.
- Pipeline отправляет summary с list of failed objects owner.

### [A3] Rate limit — pipeline backs off

- На шаге 7 после 30 объектов: API returns 429 Too Many Requests + Retry-After: 60.
- Pipeline ждёт; retry; если снова 429 — exponential backoff.
- Eventually finishes.
- Audit logs rate-limit events (informational).

### [A4] Quota exceeded — pipeline aborts

- На шаге 6: `POST /api/projects/{id}/run` returns 402 Payment Required (org exceeded model_executions quota for month).
- Pipeline aborts; uploads remaining tasks queue to retry next billing cycle.
- Owner notified via email + dashboard alert.

### [A5] Service key rotation

- Каждые 90 дней (или по policy) Org Admin ротирует key.
- В Settings → service account → Rotate Key.
- Старый key valid for 7-day grace period; new key issued.
- Org Admin updates external secret manager в течение grace period.
- После grace period — старый key invalidated.

---

## Потоки исключений

### [E1] Service key compromised — emergency revoke

- Org Admin → Settings → service account → Revoke (immediate).
- Все in-flight + future requests rejected с 401.
- Audit: `actor_revoked` + reason.
- Pipeline owner alerted out-of-band.

### [E2] Service попадает в RLS context error

- Если service token не connected к dept correctly: queries return empty.
- Должен быть unit-test: service auth → dept context properly set.

### [E3] Bulk run interrupted (FASTSAAS down mid-run)

- Pipeline должен быть idempotent: с тем же `intent_hash` retry безопасен.
- FASTSAAS реализует idempotency check (per design.md §6 хотя deferred — но для bulk это P1).
- *Note:* idempotency cache становится высокоприоритетной для UC-005, может потребоваться раньше чем планировалось.

---

## Бизнес-правила

- **BR-030:** Service account имеет org-level scope, может быть restricted к одному department.
- **BR-031:** Service не имеет UI login; только API key authentication (BR-explicit; не overload password flow).
- **BR-032:** Bulk operations с одним `X-FASTSAAS-Intent-Hash` header группируются в audit для replay/review.
- **BR-033:** Service quotas измеряются в model_executions per month (или per calendar period).
- **BR-034:** Partial failure не abort вся batch; per-object failure logged but other succeed.
- **BR-035:** Service key rotation — built-in grace period (default 7 days).
- **BR-036:** Service не может invite users, modify org settings, share projects (только operational scope).

---

## Открытые вопросы

- [ ] Service actor type: новый `actor_type=SERVICE` (per UC-007) vs designated HUMAN parent? *Это decision UC-007.*
- [ ] Idempotency: для bulk критично; раньше планировалось отложить (design.md §6). Поднимать в v1? *Предложение: yes; bulk-via-API критичен для Globex-сценария.*
- [ ] Quotas: per-org или per-service-account? *Предложение: per-org overall + per-service soft cap.*
- [ ] Webhook callbacks: pipeline может subscribe to events «execution finished»? *Предложение: nice-to-have, отдельный feature.*

---

## Связь с архитектурными решениями

- **ADR-008 (auth):** API key flow extends магик-ссылку pattern; key как primary credential.
- **ADR-009 (actors):** требует решения по `actor_type=SERVICE` (см. UC-007).
- **ADR-010 (audit):** intent_hash bulk-grouping уже поддерживается; intent_metadata.batch_id — новое поле в pattern.
- **design.md §6 (intent_hash):** UC-005 поднимает приоритет idempotency cache — может перевестись из «отложено» в «v1».
- **Будущий ADR-013 (Authorization):** scope vocabulary для service — конкретный пример того, что решение должно поддерживать.
