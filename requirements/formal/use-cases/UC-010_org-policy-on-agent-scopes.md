---
id: UC-010
title: Org Admin устанавливает policy на capabilities AGENT и SERVICE actors
level: Цель пользователя (administrative / governance)
priority: high
status: draft
created: 2026-05-01
author: Artem Konuchov (с Claude Code)
traces_to:
 related_features:
 - FE-CORE-3 # Audit с governance angle
 related_adr:
 - ADR-009 # Actor model
 - ADR-010 # Audit log
 related_use_cases:
 - UC-003 # Personal AI agent (governs)
 - UC-005 # Bulk pipeline service
 - UC-007 # Org-level service account
 related_epic: the SaaS-core epic # Foundation; full policy DSL — Phase 2
---

# UC-010: Org Admin устанавливает policy на capabilities AGENT и SERVICE actors

**Уровень:** Цель пользователя (administrative / governance)
**Приоритет:** Высокий (для compliance-чувствительных org)
**Акторы:**
- **Org Admin** (HUMAN, role owner / admin)
- **Compliance Officer** (HUMAN, отдельная org-level role per UC-002)

**Связанные требования:** FE-CORE-3 (audit with governance angle)

---

## Краткое описание

Крупная организация (compliance-driven, например Globex) устанавливает org-wide policy для capabilities AGENT и SERVICE акторов. Например: «никакой AGENT в этой org не может delete projects», «SERVICE accounts не могут writes к данным после 22:00 CET», «AGENT actions требуют HUMAN approval для transactions > high-value». Policy enforced на запросе capabilities (provisioning) и на запросе действий (runtime).

## Предусловия

- Org Admin или Compliance Officer аутентифицирован.
- Authorization model (capabilities-based per будущий ADR-013) реализована.
- Policy storage / enforcement engine реализован.

## Постусловия (успех)

- Policy сохранена.
- Provisioning AGENT/SERVICE с capabilities, противоречащими policy — блокирован (нельзя выдать).
- Существующие AGENT/SERVICE с capabilities, теперь противоречащими policy — capabilities помечены как `policy_blocked`; runtime checks отклоняют.
- Audit-row сохраняет policy change с before/after diff.

## Постусловия (неудача)

- Если policy DSL invalid — reject с syntax error.
- Если policy конфликтует с existing critical operations — admin предупреждён, должен подтвердить «Apply with override».

---

## Основной поток

| # | Актор (Org Admin) | Система |
|---|-------------------|---------|
| 1 | Settings → Governance → Agent Policies | |
| 2 | | Показывает текущие policies (если есть) и форму для новой |
| 3 | Создаёт policy: «No AGENT may have `delete:*` capability» | |
| 4 | | Парсит DSL (или structured form), validates |
| 5 | | Проверяет existing capabilities: 3 AGENTs имеют `delete:scenario` |
| 6 | | Показывает Org Admin: «3 existing capabilities будут заблокированы. Continue?» |
| 7 | Org Admin подтверждает | |
| 8 | | Сохраняет policy; помечает 3 capabilities как `policy_blocked=true`; не удаляет, чтобы при unblock'е policy могли восстановиться |
| 9 | | Audit «policy_created» + «capabilities_blocked» (3 строки) |
| 10 | | Уведомления HUMAN-владельцам пострадавших AGENTs: «Your AGENT capability X is now blocked by org policy» |
| 11 | (Час спустя) AGENT пытается выполнить delete | |
| 12 | | Capability check: capability существует, но `policy_blocked=true` → reject 403; audit «policy_enforced_denial» |

---

## Альтернативные потоки

### [A1] Time-based policy

- Policy: «No SERVICE writes between 22:00 and 06:00 CET» (например, для backup window).
- Enforcement engine оценивает text + current time per request.
- Если SERVICE attempts write at 03:00 — reject; audit показывает policy reason.

### [A2] Threshold-based approval policy

- Policy: «AGENT actions affecting > 10 entities или valued > high-value require HUMAN approval».
- AGENT requests bulk delete 50 scenarios.
- Capability check: hits threshold → returns `requires_approval: true` + token URL (как в UC-003 [A2]).
- HUMAN approves → continue.

### [A3] Department-scoped policy

- Compliance Officer устанавливает policy для конкретного department: «In Risk dept, AGENT cannot run models without HUMAN review».
- Other departments не affected.

### [A4] Policy override (emergency)

- Critical incident: AGENT нужно выполнить blocked action.
- Org Owner может temporarily override policy (TTL 1 hour).
- Override logged with extreme prejudice (special audit + Slack alert + email).

### [A5] Policy versioning / rollback

- Org Admin изменяет policy.
- System keeps history; admin может rollback к prior version.
- Audit показывает full lineage policy changes.

---

## Потоки исключений

### [E1] Policy DSL invalid

- На шаге 4: parser fails.
- Inline error на форме с position и suggestion.

### [E2] Policy создаёт deadlock с system requirements

- На шаге 5: новая policy блокирует internal FASTSAAS operations (например, system audit logger).
- Reject с message «Policy conflicts with system: cannot block X».

### [E3] Compliance Officer пытается applied policy без owner approval

- В стрictly governed orgs: critical policies (delete restrictions, etc.) требуют owner co-sign.
- Compliance Officer initiates → Owner notified → approval flow.

---

## Бизнес-правила

- **BR-044:** Policy applied на capabilities, не на actions напрямую (capabilities — единица контроля per ADR-013).
- **BR-045:** Org Admin / Compliance Officer могут set policies; member-level НЕ могут.
- **BR-046:** Policies have priority levels: org > department > resource-specific.
- **BR-047:** Existing capabilities, conflicting с new policy, помечены `policy_blocked` (не удалены), чтобы unblock на rollback policy восстанавливал capability.
- **BR-048:** Policy enforcement runs on every capability check (not cached aggressively — staleness риск compliance issue).
- **BR-049:** Policy changes — audit-able с full diff; audit immutable per ADR-006.
- **BR-050:** Override mechanism — explicit, time-limited, heavily logged.

---

## Открытые вопросы

- [ ] **Policy DSL syntax:** declarative YAML, simple list of rules, or custom expression language? *Предложение для v1: structured form (UI), backed by simple JSON rules — DSL в Phase 2.*
- [ ] **Default policies for new org:** sensible defaults («AGENTs cannot delete by default»)? *Предложение: yes, secure-by-default.*
- [ ] **Policy templates:** library of common policies (HIPAA-flavored, compliance-flavored)? *Phase 3.*
- [ ] **Cross-org policy sharing** (consultancy distributes recommended policy)? *Phase 3+.*
- [ ] **Compliance Officer role:** часть v1 или Phase 2? *Предложение: foundation в v1 (как новая org-role); full UI Phase 2.*
- [ ] **Policy enforcement performance:** O(N policies) per capability check OK, или нужно compile policies в efficient form? *Предложение: profile при ≥ 100 policies; до этого linear OK.*

---

## Связь с архитектурными решениями

- **Будущий ADR-013 (Authorization model):** policies оперируют capabilities — должно быть central concept в model.
- **ADR-010 (audit):** policy enforcement decisions сами audit-able («action denied by policy X»). Это критично для compliance.
- **UC-002 (departments):** department-scoped policies — отдельный slice.
- **UC-003, UC-005, UC-007:** все три (AGENT, SERVICE) — субъекты policies.
- **Compliance Officer role:** новая role в дополнение к owner/admin/member/viewer (см. UC-002 [A5]).
