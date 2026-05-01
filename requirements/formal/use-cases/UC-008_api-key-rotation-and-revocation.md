---
id: UC-008
title: Управление API keys — создание, ротация, отзыв
level: Цель пользователя (administrative + security)
priority: high
status: draft
created: 2026-05-01
author: Artem Konuchov (с Claude Code)
traces_to:
 related_features:
 - FE-CORE-1 # Actor-Centric Identity
 - FE-CORE-3 # Audit
 related_adr:
 - ADR-008 # Auth flow
 - ADR-009 # Actor model (refines)
 related_use_cases:
 - UC-003 # Personal AI agent (consumer of keys)
 - UC-005 # Bulk pipeline service
 - UC-007 # Org-level service account
 related_epic: the SaaS-core epic
---

# UC-008: Управление API keys — создание, ротация, отзыв

**Уровень:** Цель пользователя (administrative + security)
**Приоритет:** Высокий
**Акторы:**
- **HUMAN** (создаёт personal API key для своего scripting)
- **HUMAN parent** (создаёт API key для своего AGENT, per UC-003)
- **Org Admin** (создаёт API keys для SERVICE, per UC-005, UC-007)
- **Compliance Officer / Security responder** (emergency revocation)

**Связанные требования:** FE-CORE-1, FE-CORE-3

---

## Краткое описание

API key — долгоживущий токен для программного доступа к FASTSAAS API (в отличие от JWT для interactive UI sessions). Используется HUMAN-ами для scripting, AGENT'ами через MCP-клиенты, SERVICE'ами для cron / CI / интеграций. Этот UC описывает полный lifecycle: create → use → rotate → revoke. Включает scenarios компрометации, ротации с grace period, и emergency revocation.

## Предусловия

- Actor (HUMAN / AGENT / SERVICE) существует.
- User имеет capability `grant:api_key` на этот actor (HUMAN на самого себя; HUMAN parent на свой AGENT; Org Admin на SERVICE).
- API keys storage реализован (`api_keys` table, см. design.md Decision #15).

## Постусловия (успех)

- Key создан с уникальным sha256(token) hash в БД; raw token показан user-у один раз.
- Key используется в API requests в header `Authorization: Bearer apz_<type>_<random>`.
- Key revocation немедленно блокирует subsequent requests (Redis cache invalidation).
- Все события (create / use / rotate / revoke) попадают в `audit_log`.

## Постусловия (неудача)

- Если попытка использовать revoked key — 401 + audit entry «attempted use of revoked key».
- Если key compromised и не revoked — все актуальные actions могут быть отслежены через audit (post-incident analysis).

---

## Основной поток (Создание + Use)

| # | Актор | Система |
|---|-------|---------|
| 1 | (HUMAN) Settings → API Keys → Create New | |
| 2 | | Показывает форму: name, scope restriction (optional), expiry (optional), IP allowlist (optional) |
| 3 | Заполняет: name="My laptop Claude", scope=read+write на projects, expiry=90 days | |
| 4 | | Validates capability `grant:api_key`; если нет — 403 |
| 5 | | Generates 32-byte random → base62 encode → prepend prefix → result: `apz_human_8f3cVKtLm9pQRwzN2xYbHsT3uE6FjZ4dWqX1bYn7aP5v` |
| 6 | | Стores `sha256(token)` в `api_keys.key_hash`, prefix `apz_human_8f3c` в `api_keys.key_prefix` для display |
| 7 | | Audit: «api_key_created» с metadata (name, scope_restriction, created_by) |
| 8 | | Показывает HUMAN: full token + warning «This is the only time you'll see it. Copy now.» |
| 9 | HUMAN копирует token в свой password manager / `.env` / config | |
| 10 | (Day-to-day) HUMAN script делает `GET /api/projects/X` с `Authorization: Bearer apz_human_8f3c...` | |
| 11 | | Auth middleware: extract token → sha256 → DB lookup → cache в Redis (5min TTL) |
| 12 | | Loads actor (HUMAN); sets request context: actor_id, api_key_id, key_scope |
| 13 | | Capability check: effective = actor.capabilities ∩ key.scope_restriction; если ОК → continue |
| 14 | | Async update: `last_used_at`, `last_used_ip` |
| 15 | | Returns data; audit с `intent_metadata.api_key_id=<this key's id>` |

---

## Альтернативные потоки

### [A1] Rotation — обновление key

| # | Актор | Система |
|---|-------|---------|
| 1 | HUMAN открывает key list, делает «Rotate» на «My laptop Claude» | |
| 2 | | Mints НОВЫЙ key (новый random, новый hash) с тем же name + " (rotated)" |
| 3 | | Помечает старый key: `rotation_grace_until = NOW() + 7 days`; both keys остаются valid |
| 4 | | Показывает HUMAN новый full token + warning |
| 5 | HUMAN обновляет config в external system на новый token | |
| 6 | (Через 7 дней) Cron job revokes старый key с `revoked_reason='rotated'` | |
| 7 | | Audit: «api_key_auto_revoked_post_rotation» |
| 8 | (Опц.) HUMAN раньше grace period нажимает «Confirm rotation done» — старый revoked сразу | |

### [A2] AGENT key создаётся parent HUMAN'ом (per UC-003)

| # | Актор (HUMAN parent) | Система |
|---|----------------------|---------|
| 1 | Settings → Personal Agents → My Claude → Create New API Key | |
| 2 | | Form: name, optional scope restriction (subset of AGENT's capabilities — UI shows only those) |
| 3 | Создаёт «My laptop Claude — Asset Mgmt only» с restriction `dept_id=Asset Management` | |
| 4 | | Validates: `grant:api_key on agent:<my_claude>`; check scope restriction is subset of AGENT's caps |
| 5 | | Создаёт key с prefix `apz_agent_*`; сохраняет; показывает HUMAN |
| 6 | HUMAN копирует в `~/.config/claude-code/mcp.json` для своего Claude | |

### [A3] SERVICE key создаётся Org Admin'ом (per UC-007)

- Аналогично [A2], но prefix `apz_service_*`, scope grants org-wide или dept-scoped.
- Audit указывает `created_by=org_admin_actor_id`.

### [A4] Emergency revocation — compromised key

| # | Актор | Система |
|---|-------|---------|
| 1 | HUMAN обнаружил token публично (committed в git, в Slack screenshot, etc.) | |
| 2 | Открывает Settings → API Keys → конкретный key → Revoke | |
| 3 | | Modal: select reason "Compromised" + free-text description |
| 4 | | UPDATE api_keys SET revoked_at=NOW(), revoked_reason='compromised', revoked_by=current_actor.id, metadata.revoke_note=... |
| 5 | | Invalidates Redis cache for key_hash (immediate effect) |
| 6 | | Audit: «api_key_revoked» с reason; alerts to org admin (Slack/email) |
| 7 | (Любые subsequent requests с этим token) | 401 Unauthorized + audit «attempted_use_of_revoked_key» |

### [A5] Cascade revocation при deletion actor

- HUMAN soft-deleted (`actors.deleted_at`) → cascade trigger revokes все его api_keys.
- AGENT revoked via UC-003 [E1] → cascade revokes all его api_keys.
- Org-level: Compliance Officer выполняет «Revoke all keys for actor X» — single SQL update.

### [A6] Bulk security incident response

- Compliance Officer / Security responder обнаруживает «leak prefix `apz_service_xy3a*` opublikovan'»
- Выполняет «Revoke all keys with prefix matching X» — bulk update.
- Все затронутые pipeline owners notified out-of-band.
- Audit: bulk-revoke event с list affected keys.

### [A7] Per-key Scope restriction enforcement

- Key создан с `scope_restriction = {operations: [read], resource_types: [project]}`.
- При попытке `POST /api/projects` (write op) с этим key:
 - Auth passes (key valid).
 - Capability check: effective = actor.capabilities ∩ {read on project} → no `write` in effective set.
 - Returns 403 + audit «action_denied_by_key_scope».

---

## Потоки исключений

### [E1] Token format invalid

- Header `Authorization: Bearer some-random-string` не матчит регексу `apz_(human|agent|service)_[a-zA-Z0-9]{43}`.
- Возвращает 401 быстро без DB lookup.
- Audit (rate-limited): malformed_token attempt.

### [E2] Token valid format но не найден в БД

- Hash не находится → 401.
- Audit: unknown_token attempt с prefix (для investigation, full token не логируется).

### [E3] Token expired

- `expires_at < NOW()` — 401 с message "Key expired" (через WWW-Authenticate header).
- Audit: expired_token_attempt.

### [E4] Rate limit exceeded на key

- Если key имеет `metadata.rate_limit` — Redis-based counter exceeded.
- Возвращает 429 + Retry-After header.
- Audit: rate_limit_exceeded.

### [E5] IP not in allowlist

- Если key имеет `metadata.ip_allowlist` и client IP не матчит — 403.
- Audit: ip_allowlist_violation с IP details.

### [E6] Key не имеет capability на запрашиваемое action даже без scope_restriction

- Actor сам не имеет capability → стандартный 403 (capability denial).
- Audit: insufficient_capability с requested op + resource.

---

## Бизнес-правила

- **BR-051:** Multiple API keys per actor allowed (HUMAN/AGENT/SERVICE).
- **BR-052:** Key generated as 32-byte random, base62 encoded, with prefix `apz_(human|agent|service)_`.
- **BR-053:** Key full token shown ONCE при создании; после — только prefix + last4 для identification.
- **BR-054:** Key stored as `sha256(token)` (optionally salted — TBD); raw token never persisted.
- **BR-055:** Key может иметь optional `scope_restriction` — strict subset of actor's capabilities. Effective capabilities при request = intersection.
- **BR-056:** Revocation = soft (set `revoked_at`); key_hash сохраняется для audit и для detecting reuse.
- **BR-057:** Rotation — grace period default 7 дней с both keys valid; configurable per org policy.
- **BR-058:** При deletion actor — cascade revoke all его keys (soft).
- **BR-059:** Каждый API request с key пишет audit row с `intent_metadata.api_key_id`.
- **BR-060:** Org policy может ограничивать: max keys per actor, default expiry, IP allowlist requirement, rotation frequency.
- **BR-061:** Compliance Officer может видеть org-wide key audit + bulk-revoke (cross-actor).
- **BR-062:** Использование revoked key (post-revocation attempt) — high-priority audit + Slack alert.

---

## Открытые вопросы

- [ ] **Salt for sha256?** Полный entropy токена дает достаточно security без salt; salt = paranoid best practice (cost negligible). *Предложение: yes, salt с per-deployment secret.*
- [ ] **Default expiry:** never / 90 days / 365 days? Org policy enforce? *Предложение: never default; org может set required.*
- [ ] **HUMAN personal keys в v1 vs Phase 2?** *Предложение: yes в v1 — лёгкий add-on к AGENT/SERVICE flow.*
- [ ] **IP allowlist в v1 UI vs Phase 2?** Schema готова в v1; UI для конфигурации — Phase 2 если timeline pressure. *Предложение: schema + минимальный UI в v1.*
- [ ] **Webhook events** (key_created, key_revoked, key_used_after_revocation): v1 или Phase 2? *Предложение: Phase 2 backlog item.*
- [ ] **GitHub Secret Scanning partnership** для auto-revoke leaked keys: post-public-launch.
- [ ] **Stripe-style `_test_` vs `_live_` env distinction** в prefix: v1 или Phase 2? *Предложение: Phase 2 add-on (no schema change).*
- [ ] **Rotation frequency policy** — max key age before forcing rotation? *Предложение: org policy в Phase 2; v1 без enforcement.*
- [ ] **Multi-tenant key sharing forbidden?** Key привязан к actor → naturally scope ed. Не возникает confusion.

---

## Связь с архитектурными решениями

- **ADR-008 (Auth):** API keys — alternative auth path к JWT (для programmatic клиентов).
- **ADR-009 (Actors):** **REFINEMENT** — убрать `agents.api_key_hash` и `services.api_key_hash`; вынести в отдельную таблицу `api_keys` с FK на `actors.id`. Это позволяет multiple keys per actor + per-key scope.
- **ADR-010 (Audit):** `intent_metadata.api_key_id` ссылается на конкретный key — позволяет "show me everything done by key X" reports.
- **Decision #11 (Authorization):** capability check учитывает `key.scope_restriction` через intersection (effective_capabilities = actor.capabilities ∩ key.scope_restriction).
- **Decision #14 (Org policy):** policies могут regulate key creation rules (max per actor, required expiry, IP allowlist).
- **Будущий ADR-017** (API Keys): полностью описывает схему, lifecycle, security policies.

---

## Сценарий «компрометация без знания» — replay analysis

Если key утёк месяц назад и никто не знает:

1. Compliance Officer регулярно запускает report «keys created > 90 days ago, used recently from new IP».
2. Видит подозрительное: «My laptop Claude используется с IP 185.X.Y.Z (новый, не в IP history)».
3. Запрашивает action history этого key за последние 30 дней (filter audit by api_key_id).
4. Видит unusual operations: bulk export at 03:00 UTC.
5. Решает revoke immediately + investigate.
6. После revoke — все subsequent attempts с этим key → high-priority audit + alert.
7. Post-incident — full audit trail доступен для forensics.

Это **главная польза per-key audit** — replay даёт точный scope incident'а без guesswork.
