---
id: UC-003
title: Практик использует личного AI-агента (Claude Code через MCP) для повседневной работы
level: Цель пользователя
priority: high
status: draft
created: 2026-05-01
author: Artem Konuchov (с Claude Code)
traces_to:
 related_features:
 - FE-CORE-1 # Actor-Centric Identity (HUMAN/AGENT)
 - FE-CORE-3 # Audit Trail с intent_hash
 - FE-OPT-MCP # MCP Server (FASTSAAS-vision optional module)
 related_ar:
 - AR-3 # Orchestrator
 related_adr:
 - ADR-008 # Auth flow
 - ADR-009 # Actor model (CTI)
 - ADR-010 # Audit log
 related_epic: the SaaS-core epic # Platform SaaS core
---

# UC-003: Практик использует личного AI-агента (Claude Code через MCP) для повседневной работы

**Уровень:** Цель пользователя
**Приоритет:** Высокий
**Акторы:**
- **Practitioner** (HUMAN actor) — практик, использует Claude Code как primary IDE
- **Claude Code Agent** (AGENT actor, parent_actor_id = Practitioner) — AI-агент работает через MCP-сервер FASTSAAS

**Связанные требования:** FE-CORE-1, FE-CORE-3, FE-OPT-MCP

---

## Краткое описание

Практик работает в Claude Code (или Cursor / другом MCP-клиенте). К FASTSAAS подключён MCP-сервер. Через диалог в Claude Code практик инициирует операции в FASTSAAS: чтение данных проекта, запуск моделей, подготовку отчётов. AGENT-актор выполняет действия от имени HUMAN-актора, **в рамках выданного scope**, с audit trail и обязательным подтверждением destructive operations.

## Предусловия

- Practitioner аутентифицирован в FASTSAAS, состоит в org с правами `member` или выше.
- FASTSAAS ⇒ MCP-сервер развёрнут и доступен (либо как часть platform, либо как separate service в FE-OPT-MCP).
- Practitioner установил Claude Code (или другой MCP-клиент).
- Practitioner выполнил первичную настройку: связал свой MCP-клиент с FASTSAAS (см. альтернативный поток A1 «Initial Setup»).
- AGENT-актор существует, привязан к HUMAN, имеет capability set.

## Постусловия (успех)

- Все запрошенные действия выполнены согласно правам AGENT.
- Каждое действие записано в `audit_log` с `actor_type=AGENT`, `parent_actor_id=Practitioner`, `intent_metadata.original_prompt=<user message>`.
- Destructive actions (delete, archive, share) выполнены только после явного approval HUMAN.
- Practitioner видит в FASTSAAS web UI feed «Recent agent actions» с возможностью review.

## Постусловия (неудача)

- Если AGENT запросил действие вне своего scope — operation отклонена, audit-row создан с `action_denied=true`.
- Если HUMAN отклонил approval-prompt — операция rolled back, ничего не изменено.

---

## Основной поток (Day-to-day)

| # | Актор | Система |
|---|-------|---------|
| 1 | (Practitioner в Claude Code) Пишет: «Загрузи данные объекта *Project Alpha*, проверь что не хватает для AnalysisPipeline-A, дополни типичными значениями и запусти расчёт» | |
| 2 | (Claude Agent) Через MCP-tool вызывает `fastsaas.list_projects(name_contains="Project Alpha")` | |
| 3 | | Проверяет capability AGENT: `read:project` на org/dept Practitioner-а — OK |
| 4 | | Возвращает список матчей; пишет audit-row (`actor=AGENT`, `op=list_projects`, `intent_hash=agent:<hash>`, `intent_metadata.original_prompt="..."`) |
| 5 | (Claude) Получает project_id, вызывает `fastsaas.get_project(id)` | |
| 6 | | Аналогично: capability check + return + audit |
| 7 | (Claude) Анализирует data, видит что не указан `discount_rate`. Вызывает `fastsaas.suggest_inputs(project_id, model="analysis-pipeline-a")` (если такой tool есть) или формирует suggestions сам | |
| 8 | (Claude в чате с Practitioner) Показывает: «Не хватает discount_rate. Предлагаю 5.5% based on primary segment market 2026. ОК?» | |
| 9 | (Practitioner) Подтверждает в чате | |
| 10 | (Claude) Вызывает `fastsaas.update_project_inputs(project_id, {discount_rate: 0.055})` | |
| 11 | | Capability check: `write:project` для этого project_id — OK; обновляет inputs; audit |
| 12 | (Claude) Вызывает `fastsaas.run_model(project_id, model="analysis-pipeline-a")` | |
| 13 | | Capability check: `run:model` — OK; возвращает 202 Accepted с execution_id; audit |
| 14 | (Claude) Polls `fastsaas.get_execution_status(execution_id)` до завершения | |
| 15 | | По завершении возвращает результаты |
| 16 | (Claude в чате) Резюмирует результат для Practitioner: «NPV = the calculated value, IRR = 7.8%. Хочешь сгенерировать отчёт?» | |
| 17 | (Practitioner) Открывает FASTSAAS web UI, видит «Recent agent actions» с полным trail | |

---

## Альтернативные потоки

### [A1] Initial Setup — Practitioner впервые подключает Claude Code

| # | Актор | Система |
|---|-------|---------|
| 1 | Practitioner в FASTSAAS web UI: Settings → Personal Agents → Connect Claude Code | |
| 2 | | Показывает форму: name agent (default «My Claude»), scope set (default «read+write own projects, run models, NO delete») |
| 3 | Practitioner настраивает scope (можно сузить, нельзя расширить за пределы своих прав) | |
| 4 | | Создаёт AGENT actor с `parent_actor_id=Practitioner`, `actor_type=AGENT` (per ADR-009); генерирует API key; mint capabilities (см. ADR-013 если принято) |
| 5 | | Показывает Practitioner: API key + MCP config snippet для копирования в `~/.config/claude-code/mcp.json` |
| 6 | Practitioner копирует config и token в Claude Code | |
| 7 | Practitioner в Claude Code пишет «list my projects» | |
| 8 | (Claude) Тест tool-call → FASTSAAS | |
| 9 | | Подтверждает успех; помечает AGENT `status=active`; первый audit с `intent_metadata.first_use=true` |

### [A2] Destructive operation requires HUMAN approval

| # | Актор | Система |
|---|-------|---------|
| 1 | (Practitioner) «Удали старый scenario *Pessimistic v0*» | |
| 2 | (Claude) Tool-call `fastsaas.delete_scenario(id)` | |
| 3 | | Capability check: AGENT не имеет `delete:scenario` (по дефолту). Проверяет policy — нужна explicit user approval |
| 4 | | Возвращает Claude: 409 Conflict + payload `{requires_approval: true, approval_url: "https://app.fastsaas.com/approve/<token>"}` |
| 5 | (Claude в чате) «Действие требует подтверждения. Открой [URL] и одобри.» | |
| 6 | Practitioner открывает URL в браузере (уже залогинен как HUMAN) | |
| 7 | | Показывает: «Claude хочет удалить *Pessimistic v0*. Approve / Reject?» |
| 8 | Practitioner approves | |
| 9 | | Регистрирует one-time approval token; audit «human_approved_agent_action» |
| 10 | (Claude) Получает webhook / polls и retries delete с approval token | |
| 11 | | Выполняет delete; audit чётко указывает «AGENT action approved by HUMAN at <timestamp>» |

### [A3] AGENT просит разовое расширение scope

- Если в шаге A2-3 AGENT хочет выполнить действие вне scope (не просто destructive — а вообще запрещённое):
- Возвращает 403 + диалог «Запрос расширения scope». 
- HUMAN решает: одобрить one-time, добавить в постоянный scope, или отказать.

### [A4] Несколько AGENT-актора у одного HUMAN

- Practitioner имеет 2 AGENT-актора: «My Claude» (для оценок) и «My Cursor» (для других задач).
- Каждый имеет свой API key + scope set.
- В audit_log различимы по `actor_id`.

### [A5] Replay agent session

- Practitioner смотрит «Recent agent actions» → выбирает session → видит chronological trail с full diffs.
- Кнопка «Reproduce»: создаёт новую project copy и выполняет тот же sequence — для verification / what-if.

---

## Потоки исключений

### [E1] AGENT token compromised — emergency revoke

- Practitioner в Settings → Personal Agents → revokes «My Claude».
- Все active sessions invalidated мгновенно.
- Любые in-flight operations этого agent отклоняются.
- Audit: `actor_revoked` event.

### [E2] AGENT превысил rate limit

- Tool-call возвращает 429 Too Many Requests.
- Claude должен degrade gracefully (не retry бесконечно).
- Audit: rate-limit event.

### [E3] HUMAN закончил session, AGENT всё ещё активен

- AGENT сохраняет независимость: его capability set действует пока не revoked HUMAN'ом или token не expired.
- Это feature, не bug: AGENT может выполнить долгий job в фоне после того как HUMAN закрыл лаптоп.

### [E4] Capability check returns false negative из-за RLS context

- AGENT auth-context строится без `SET LOCAL app.current_org` корректно — операция fails с 404 (per ADR-007).
- Должна быть отдельная миддлварь для AGENT context-setup.

---

## Бизнес-правила

- **BR-015:** AGENT всегда имеет `parent_actor_id` = HUMAN, который его создал (per ADR-009).
- **BR-016:** AGENT capability — **строгое подмножество** capability HUMAN parent (cannot escalate).
- **BR-017:** Destructive operations (`delete:*`) НЕ входят в default scope AGENT — требуют explicit grant либо per-action approval.
- **BR-018:** AGENT в audit_log всегда имеет `parent_actor_id` denormalised для filtering (per ADR-010).
- **BR-019:** AGENT API key хранится как `sha256` (per ADR-008 magic-link pattern).
- **BR-020:** При revocation AGENT все его active sessions немедленно invalidated.
- **BR-021:** При soft-delete HUMAN (`deleted_at`) — все его AGENTs cascade soft-delete.
- **BR-022:** AGENT не может создавать sub-AGENTs (parent chain depth = 1).
- **BR-023:** Каждое действие AGENT обязательно с `intent_metadata.original_prompt` (если был prompt от HUMAN).

---

## Открытые вопросы

- [ ] Approval flow в [A2]: in-band webhook to MCP, или out-of-band browser-only? *Предложение: гибрид — Claude получает URL, HUMAN открывает в браузере, Claude polls статус.*
- [ ] Scope DSL: список constraints (`read:project`, `write:scenario`) vs выражения (`if dept=acquisitions then read`)? *Предложение для v1: список; constraint-expressions в Phase 2.*
- [ ] One-time approval vs grant-permanently UX в [A2]: всегда оба варианта или только одно? *Предложение: оба, default = one-time для destructive.*
- [ ] Token format: opaque API key (`apz_AGENT_<random>`) vs JWT? *Предложение: opaque + Redis lookup для revocation immediacy.*
- [ ] Public vs private agent registration: HUMAN регистрирует agent сам, или через invitation от admin? *Предложение для v1: self-service для personal AGENTs; org-level service AGENTs (UC-005, UC-007) — через admin.*

---

## Связь с архитектурными решениями

- **ADR-009 (actors CTI):** AGENT actor type уже предусмотрен; этот UC уточняет capabilities + lifecycle.
- **ADR-008 (auth):** AGENT использует API key (не password / OAuth); rotating revoke-friendly.
- **ADR-010 (audit):** AGENT actions с `parent_actor_id` denormalised + `original_prompt` в `intent_metadata`.
- **Будущий ADR-013 (Authorization):** capability scope для AGENT — central piece этого UC.
- **Будущий MCP epic:** FASTSAAS MCP-сервер — отдельный compound, FE-OPT-MCP в FASTSAAS-vision.
