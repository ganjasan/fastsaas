---
id: UC-007
title: Организация заводит service account без человеческого parent (для бот-сервисов и интеграций)
level: Цель пользователя (administrative)
priority: high
status: draft
created: 2026-05-01
author: Artem Konuchov (с Claude Code)
traces_to:
 related_features:
 - FE-CORE-1 # Actor-Centric Identity
 related_adr:
 - ADR-009 # Actor model (CTI) — extends actor_type vocabulary
 related_use_cases:
 - UC-005 # Bulk pipeline service (caller)
 related_epic: the SaaS-core epic
---

# UC-007: Организация заводит service account без человеческого parent

**Уровень:** Цель пользователя (administrative)
**Приоритет:** Высокий
**Акторы:**
- **Org Admin** (HUMAN actor, owner / admin role)
- **Service Account** (новая сущность — `actor_type=SERVICE`?)

**Связанные требования:** FE-CORE-1, расширение ADR-009

---

## Краткое описание

Организация хочет завести **сервисный аккаунт без HUMAN-владельца** — для автоматизаций (UC-005 bulk pipeline), интеграций (Slack-bot, мониторинг), или org-wide AI-сервисов (например, Globex внутренний LLM-pipeline для quality checks). Сейчас в ADR-009 актор должен быть либо HUMAN, либо AGENT с обязательным `parent_actor_id=HUMAN`. Этот UC заявляет необходимость **третьего actor type — `SERVICE`** — без HUMAN parent, owned org'ом, identifiable.

## Предусловия

- Org существует, Org Admin аутентифицирован, role `owner` или `admin`.
- Решение об actor type принято (этот UC зависит от ADR-013 / расширения ADR-009).

## Постусловия (успех)

- Создан actor с `actor_type=SERVICE`, `parent_actor_id=NULL`, привязан к organisation_id.
- Service имеет: name, description, owner_actor_id (HUMAN-admin кто создал — НЕ parent в иерархии actor, а ответственный), API key, scope set.
- В audit_log identifiable: «выполнено via Globex Compliance Service» (не «via system»).
- Service deletable owner-ом или org admin.

## Постусловия (неудача)

- Если actor_type=SERVICE не реализован — fall back на designated HUMAN as parent (workaround), audit identifiability страдает.

---

## Основной поток

| # | Актор (Org Admin) | Система |
|---|-------------------|---------|
| 1 | Settings → Service Accounts → New Service Account | |
| 2 | | Form: name, description, scope set (capabilities), responsible HUMAN owner (для notifications, billing-attribution) |
| 3 | Создаёт «Globex Compliance Audit Service»: scope = `read:audit_log`, owner = Compliance Officer | |
| 4 | | Создаёт actor: `actor_type=SERVICE`, `parent_actor_id=NULL`, `display_name="Globex Compliance Audit Service"` |
| 5 | | Создаёт связь в `service_accounts` table: `actor_id`, `org_id`, `owner_human_actor_id`, `description` |
| 6 | | Mints capabilities для AGENT (per ADR-013): `read:audit_log` org-level |
| 7 | | Generates API key; показывает один раз для копирования |
| 8 | Org Admin копирует key в integration (e.g., внешний compliance dashboard) | |
| 9 | | Service ready; audit «service_created» с указанием owner для accountability |

---

## Альтернативные потоки

### [A1] Service ownership transfer

- Owner HUMAN покидает organisation; admin меняет ownership service account на другого HUMAN.
- Service сам не меняется (тот же actor, тот же API key); меняется только attribution «notifications go to...».

### [A2] Service используется в межорганизационной интеграции

- Например, аудиторская фирма имеет access к нескольким Globex departments.
- Каждый client (Globex) создаёт service account для аудитор-firm, выдаёт scope, делится API key с external.
- Audit чётко показывает что произошло under service account, и какая HUMAN-оригиналь был attribution.

### [A3] Service automatic provisioning через Org admin API

- Org с многочисленными integrations имеет infrastructure-as-code (Terraform-style).
- Org Admin endpoint: `POST /api/admin/service_accounts` для создания через API.
- Returns service definition + API key.

---

## Потоки исключений

### [E1] Org Admin пытается создать service account для запрещённой scope

- На шаге 6: requested scope `admin:org` (т.е. service сам станет org admin).
- Reject (BR-038): service не может иметь admin-уровневые capabilities — только operational.

### [E2] Service deleted while in active use

- Org Admin удаляет service account.
- Все pending requests in-flight отклоняются.
- External pipeline видит 401, должен быть готов к этому.

---

## Бизнес-правила

- **BR-037:** SERVICE actor type — третий actor type (HUMAN, AGENT, SERVICE).
- **BR-038:** SERVICE НЕ может иметь admin-уровневые capabilities (`admin:org`, `delete:org`); только operational.
- **BR-039:** SERVICE имеет responsible HUMAN owner (для notifications, accountability), но это **не** parent_actor_id (otherwise цепляет жизненный цикл с HUMAN, что нежелательно — HUMAN может уйти, service остаётся).
- **BR-040:** SERVICE не имеет UI login; только API key authentication.
- **BR-041:** SERVICE attributable в audit как «service: <name>» — не сливается с HUMAN audit.
- **BR-042:** При deletion org → cascade на services (soft-delete per ADR-006).
- **BR-043:** Org-level policy может ограничивать quota services per org.

---

## Открытые вопросы

- [ ] **Решение:** новый `actor_type=SERVICE` или workaround с designated HUMAN as parent? *Анализ:*
 - **Pro `actor_type=SERVICE`:** чисто semantically, audit identifiability, lifecycle independence, расширяет ADR-009 элегантно.
 - **Pro designated HUMAN:** не требует изменения ADR-009, проще migration.
 - **Рекомендация:** `actor_type=SERVICE`. Расширение minimal (1 enum value + 1 child table); audit story значимо лучше.
- [ ] Может ли SERVICE создавать свои AGENTs? (например, service-spawned ad-hoc workers) *Предложение для v1: нет; depth=1.*
- [ ] Service rate-limits per service vs per org? *Предложение: per-service для granular control + per-org overall ceiling.*
- [ ] Service public/private: org может публиковать service для external partners? *Предложение для v1: нет; cross-org через explicit grants.*
- [ ] Webhooks за service: subscribe to events? *Backlog — отдельный feature.*

---

## Связь с архитектурными решениями

- **ADR-009 (actors CTI):** требует extension — добавить `actor_type=SERVICE` в CHECK constraint, добавить `services` child table:
 ```sql
 CREATE TABLE services (
 actor_id UUID PRIMARY KEY REFERENCES actors(id) ON DELETE CASCADE,
 organisation_id UUID NOT NULL REFERENCES organisations(id),
 owner_actor_id UUID NOT NULL REFERENCES actors(id), -- responsible HUMAN
 api_key_hash TEXT NOT NULL,
 description TEXT,
 last_used_at TIMESTAMPTZ NULL
 );
 ```
- **ADR-009 CHECK update:** `CHECK (actor_type IN ('HUMAN','AGENT','SERVICE'))`; SERVICE has `parent_actor_id IS NULL` invariant.
- **Будущий ADR-013 (Authorization):** SERVICE capabilities — bounded by org admin policy; не может escalate.
- **ADR-010 (audit):** `actor_type=SERVICE` denormalised в audit_log как обычно; для service отображения в UI используем `services.description`.
- **UC-005 (bulk pipeline):** конкретный пример SERVICE в действии.
