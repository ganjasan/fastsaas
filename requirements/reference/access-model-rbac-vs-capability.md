---
title: "Access Model — RBAC vs Capability-based для FASTSAAS"
created: 2026-05-01
status: research
purpose: "Сравнительный анализ моделей авторизации перед принятием decision #11 в spike platform-saas-core-architecture"
related:
 - "[[../decisions/ADR-007_multi-tenant-isolation]]"
 - "[[../decisions/ADR-009_actor-model-cti]]"
 - "[[../formal/use-cases/UC-001_practitioner-shares-readonly-with-client]]"
 - "[[../formal/use-cases/UC-002_organization-departments-isolated-modeling]]"
 - "[[../formal/use-cases/UC-003_personal-ai-agent-via-mcp]]"
 - "[[../formal/use-cases/UC-005_bulk-pipeline-service]]"
 - "[[../formal/use-cases/UC-007_org-level-service-account]]"
 - "[[../formal/use-cases/UC-010_org-policy-on-agent-scopes]]"
---

# Access Model — RBAC vs Capability-based для FASTSAAS

## TL;DR

**Рекомендация:** **гибридная модель** — capabilities как underlying primitive, **role bundles как presentation layer**. Это даёт:
- Familiar mental model для compliance / admin (роли).
- Гибкость capability-based для AI agents, guests, services, time-limited shares.
- Единственный механизм enforcement (capability check) при разной семантике на frontend.

Аналог: **AWS IAM**, **Google Cloud IAM**, **HashiCorp Vault** — все они начинались как RBAC, эволюционировали в hybrid.

---

## Контекст

После формализации UC-001..UC-010 стало ясно: pure RBAC не покрывает все access-сценарии FASTSAAS.

Сложности с pure RBAC:
- **UC-001:** клиент практик — не member org практик; нужен per-project access без org-membership.
- **UC-003:** AGENT имеет capabilities **уже' тоньше** чем роли HUMAN; scope intersection.
- **UC-005, UC-007:** SERVICE actors — не присваиваются роли в человеческом смысле; имеют operational scope.
- **UC-010:** policies оперируют **capabilities**, не **ролями**; «no AGENT can delete» — это capability constraint.

Все эти сценарии естественно описываются capability terminology.

---

## Часть 1: Что такое RBAC

**Role-Based Access Control** — модель, где user принадлежит к одной (или нескольким) ролям, и роль определяет permissions.

```
User --has--> Role --grants--> Permissions

Example:
 user_X is in role 'admin' → can do (read, write, delete) on (any project)
 user_Y is in role 'viewer' → can do (read) on (any project)
```

### Pros RBAC

- **Знакомо** — классика enterprise (Active Directory, LDAP, SAP).
- **Compliance-friendly** — SOC-2, ISO 27001, industry-specific compliance всё описывают через роли.
- **Простое выделение privileges** — change role = change all permissions atomically.
- **Простой query «кто admin?»** → `WHERE role='admin'`.

### Cons RBAC

- **Coarse granularity** — нельзя разрешить «user X edit project Y, но только viewer для Z» без ввода resource-level permissions.
- **Privilege creep** — со временем у пользователей накапливаются permissions, потому что cleanup сложен.
- **Sharing/delegation болезненны** — нужно либо ad-hoc role-assignments, либо новые роли для каждой комбинации.
- **AGENT/AI scope не вписывается** — AGENT = «такой-то tiny subset HUMAN роли» — отдельный механизм нужен.

---

## Часть 2: Что такое Capability-based access

**Capability** = **token** (физический или logical), который **является** authorization. Если ты держишь capability — ты можешь выполнить указанное действие. Никакого централизованного «check role» — только проверка наличия capability.

Идея originally от EROS, KeyKOS, E language; современное воплощение — POSIX capabilities, Pony, Capsicum, AWS IAM policies, Google Cloud IAM.

```
Actor --holds--> Capability(operation, resource, conditions)

Example:
 capability = (read, project:Office-Tower, [no conditions], expires_never)
 → actor с этим capability может read project Office-Tower
 → actor БЕЗ capability на этот project не может, даже если он admin org
```

### Object-capability vs ACL distinction

- **ACL (Access Control List):** «у каждого ресурса есть список actors с правами». Look-up идёт от resource.
- **Capability:** «у каждого actor есть set of capabilities». Look-up идёт от actor.

Capability модель легче масштабируется при много actors, мало per-actor capabilities.

### Pros Capability-based

- **Fine granularity natively** — capability на конкретный resource, conditions, expiry.
- **Sharing trivial** — выдать capability другому actor (с attenuation = более узким scope).
- **Time-limited / conditional access** — capability со встроенным expiry или conditions.
- **AI scope естественно** — AGENT просто получает narrow set of capabilities.
- **Cross-tenant guest** — capability не требует membership в org.
- **Audit более информативный** — каждое action references конкретную capability use.

### Cons Capability-based

- **Storage** — много row'ов. Для 1000 users × 50 projects × 5 ops = potentially 250K capabilities.
- **Performance** — каждый request = capability lookup. Нужен кэш.
- **Less familiar** — admin / compliance не привыкли мыслить capabilities.
- **Revocation сложнее** — нужно invalidate per-capability, не «change role».
- **Initial provisioning verbose** — без role bundles каждый new user требует mint-а множества capabilities.

---

## Часть 3: Сравнительная таблица для FASTSAAS use cases

| Use case | RBAC | Capability-based | Hybrid |
|----------|:----:|:----------------:|:------:|
| UC-001 Per-project guest access | ❌ Нужны ad-hoc role «guest_per_project_X» — не масштабируется | ✅ Mint capability `(read, project:X)` — natural | ✅ Capability + UI shows как «guest viewer на project X» |
| UC-002 Org → Department → Project hierarchy + roles | ✅ Departmental roles `dept_lead`, `dept_member` | ✅ Capability scope с `dept_id` condition | ✅ Bundle 'dept_lead' = capabilities на dept resources |
| UC-003 AGENT acting on behalf of HUMAN | ⚠️ AGENT-роли как «attenuated HUMAN role» — overcomplex | ✅ AGENT получает subset HUMAN's capabilities | ✅ |
| UC-005 Bulk SERVICE | ⚠️ Service-роль не вписывается в HUMAN-centric RBAC | ✅ SERVICE с specific capabilities | ✅ Bundle 'bulk-service' = read+write+run на dept |
| UC-007 SERVICE без HUMAN parent | ⚠️ Service выглядит как «user with system role» | ✅ Native fit | ✅ |
| UC-010 Org policy «no AGENT delete» | ⚠️ Полиси на роли — но AGENT scope не role | ✅ Policy = constraint на capability provisioning | ✅ |
| Compliance audit «show all admins» | ✅ Trivial query `WHERE role='admin'` | ⚠️ `WHERE capabilities CONTAINS 'admin:org'` — needs derive | ✅ Query bundle name = «derived role» |
| Mass revocation «remove all access for X» | ✅ Set role=NULL | ⚠️ Bulk-revoke all capabilities for actor | ⚠️ Same |
| Time-limited access «client view 90 days» | ⚠️ Cron job + role-assignment с expiry | ✅ Native — `expires_at` на capability | ✅ |

**Победитель по 7/9 сценариям:** capability-based (или hybrid).

---

## Часть 4: Hybrid model — детали

Идея: **capabilities — единственный механизм enforcement; роли — preset bundles, presentation only**.

### Schema

```sql
CREATE TABLE capabilities (
 id UUID PRIMARY KEY, -- UUID v7 per ADR-006
 actor_id UUID NOT NULL REFERENCES actors(id),
 operation TEXT NOT NULL, -- 'read' | 'write' | 'delete' | 'run' | 'admin' | 'share' | 'grant'
 resource_type TEXT NOT NULL, -- 'organisation' | 'department' | 'project' | 'scenario' | 'audit_log' | '*'
 resource_id UUID NULL, -- NULL = type-wide; specific UUID otherwise
 conditions JSONB DEFAULT '{}', -- {dept_id, ip_allowlist, time_window, threshold,...}
 bundle_name TEXT NULL, -- 'role:owner', 'role:guest_viewer', NULL для one-off
 granted_by UUID REFERENCES actors(id), -- кто issued
 granted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 expires_at TIMESTAMPTZ NULL, -- NULL = never
 revoked_at TIMESTAMPTZ NULL, -- soft-revoke, можно unrevoke
 policy_blocked BOOLEAN NOT NULL DEFAULT FALSE, -- per UC-010
 metadata JSONB DEFAULT '{}' -- свободные поля (intent, source)
);

CREATE INDEX idx_cap_lookup
 ON capabilities (actor_id, operation, resource_type, resource_id)
 WHERE revoked_at IS NULL AND policy_blocked = FALSE;

CREATE INDEX idx_cap_bundle
 ON capabilities (actor_id, bundle_name)
 WHERE revoked_at IS NULL;
```

### Role bundles в коде

```python
# fastsaas/auth/role_bundles.py
ROLE_BUNDLES: dict[str, list[CapabilitySpec]] = {
 "role:owner": [
 ("admin", "organisation", "self_org"),
 ("admin", "department", "all_in_org"),
 ("admin", "project", "all_in_org"),
 ("share", "project", "all_in_org"),
 ("read", "audit_log", "all_in_org"),
 #...
 ],
 "role:admin": [
 ("admin", "department", "all_in_org"),
 ("admin", "project", "all_in_org"),
 ("share", "project", "all_in_org"),
 ("read", "audit_log", "all_in_org"),
 ],
 "role:member": [
 ("read", "organisation", "self_org"),
 ("read", "department", "self_dept"),
 ("write", "project", "self_dept"),
 ("run", "model", "self_dept"),
 ],
 "role:viewer": [
 ("read", "organisation", "self_org"),
 ("read", "project", "self_dept"),
 ],
 "role:dept_lead": [
 ("admin", "department", "self_dept"),
 ("share", "project", "self_dept"),
 ("read", "audit_log", "self_dept"),
 ],
 "role:guest_viewer": [
 ("read", "project", "specific"), # specific project_id at grant time
 ],
 "role:compliance_officer": [
 ("read", "audit_log", "all_in_org"),
 ],
}
```

### Provisioning при role assignment

```python
def assign_role(actor: Actor, role: str, scope: dict) -> None:
 """
 Mint все capabilities из bundle, tag bundle_name=role.
 При role change — revoke старого bundle и mint нового.
 """
 bundle = ROLE_BUNDLES[role]
 for op, res_type, res_scope in bundle:
 resource_id = resolve_scope(res_scope, scope) # 'self_dept' → dept_id
 Capability.create(
 actor_id=actor.id,
 operation=op,
 resource_type=res_type,
 resource_id=resource_id,
 bundle_name=role,
 granted_by=current_actor.id,
 )
```

### Capability check at runtime

```python
def can(actor: Actor, op: str, resource: Resource) -> bool:
 """
 Check has actor any active, non-blocked capability matching op+resource.
 """
 return Capability.exists(
 actor_id=actor.id,
 operation=op,
 resource_type=resource.type,
 # resource_id matches specific OR NULL (type-wide):
 resource_id__in=[resource.id, None],
 revoked_at__isnull=True,
 policy_blocked=False,
 expires_at__gt=now() if expires_at_not_null else None,
 )
 # + conditions evaluation (dept match, time window, etc.)
```

### Frontend — admin sees roles, internally capabilities

```
UI:
 ┌─ Members ─────────────────────────────────┐
 │ user@example.com role: admin [edit] │
 │ user2@example.com role: member [edit] │
 │ user3@example.com role: viewer [edit] │
 │ external@partner.com role: guest_viewer │
 │ on Project «Project Alpha» │
 └────────────────────────────────────────────┘

Internally:
 user@example.com → 7 capabilities tagged bundle_name='role:admin'
 external@partner.com → 1 capability: read project:office-tower
 (bundle_name='role:guest_viewer')
```

Compliance officer запрос «show me all admins»:
```sql
SELECT DISTINCT a.* FROM actors a
JOIN capabilities c ON c.actor_id = a.id
WHERE c.bundle_name = 'role:admin'
 AND c.revoked_at IS NULL;
```

То же что в pure RBAC — `bundle_name` плёт ту же роль query-side.

---

## Часть 5: Aдвокатное против hybrid

### Аргумент 1: «Capabilities — overengineering для small SaaS»

Возможно правда для проекта с 10 users и фиксированным 4-roles. FASTSAAS:
- **UC-001** уже требует per-project access (вне role).
- **UC-003-007** требуют AGENT/SERVICE scope (вне role).
- **UC-010** требует policy на capabilities.

То есть capability-механизм всё равно нужен. Hybrid даёт его одним способом, без дублирования RBAC + per-resource ACL отдельно.

### Аргумент 2: «Performance — каждый запрос check capability»

Mitigations:
- Index `(actor_id, operation, resource_type, resource_id)` — O(log N) lookup.
- Кэш role-bundle expansion в Redis (per-session).
- При role assignment предmaterialize все capabilities — нет дополнительных computations runtime.
- For 1000 active users × 50 capabilities each = 50K rows; sub-millisecond lookup.

### Аргумент 3: «Mass revocation сложнее»

Mitigation: `revoke_all_for_actor(actor_id)` — single query update:
```sql
UPDATE capabilities SET revoked_at = NOW() WHERE actor_id = ?;
```

Same complexity as role-based revocation.

### Аргумент 4: «Compliance auditors не привыкли к capabilities»

Mitigation: UI и reports показывают **roles** (bundle_name). Auditor видит «admin», «member», «viewer» — knows the model. Capabilities — implementation detail.

---

## Часть 6: Migration story

Если изначально build pure RBAC, потом мигрировать в capabilities — болезненно (схема меняется, refactor checks).

Если build hybrid с самого начала — start с минимального set bundles, add capabilities ad-hoc по мере необходимости. Без refactor.

**Это сильнейший аргумент за hybrid в FASTSAAS:**мы знаем что AGENT, SERVICE, guests, departments, policies придут. Заложить capability primitive в bootstrap дешевле чем мигрировать на 6 месяцев.

---

## Часть 7: Industry references

| Система | Underlying model | Surface (admin sees) |
|---------|------------------|----------------------|
| **AWS IAM** | Policies (capabilities) attached to users/roles | "Roles" + inline policies (hybrid) |
| **GCP IAM** | Bindings (resource → role → member) | Roles (predefined + custom) — but each role is policy bundle |
| **GitHub** | Per-resource role + base permission + per-actor overrides | Roles per resource + "you have admin on repo X, write on repo Y" |
| **Linear** | Workspace role + team role + project role | Roles per scope |
| **HashiCorp Vault** | Policies (HCL) granting capabilities to paths | Tokens with attached policies |
| **PostgreSQL (RLS+roles)** | Roles + RLS policies (capabilities-like for rows) | Roles |
| **Kubernetes RBAC** | Role + RoleBinding + ClusterRole + ClusterRoleBinding | "Roles" (but each role is a list of capabilities) |

**Все они hybrid.** Pure RBAC не существует в production-grade systems. Pure capability-based (E, KeyKOS) — academic.

---

## Часть 8: Конкретное предложение для FASTSAAS

### Что фиксируем в spike #17 (decision #11)

1. **Capability — primary primitive.** Schema выше.
2. **Bundle-name = role label.** 6 default bundles (per Hybrid spec выше).
3. **Granularity:** per-resource capabilities possible; default — bundle-driven.
4. **AGENT/SERVICE scope:** capabilities, not roles. Bundle = optional.
5. **Per-project guest:** capability с `resource_id`, `bundle_name='role:guest_viewer'`.
6. **Department-scope:** capability с `conditions={"dept_id": "<uuid>"}`.
7. **Revocation:** soft via `revoked_at`; mass-revoke via update.
8. **Policy enforcement:** policy = filter on capability provisioning + runtime check.
9. **Audit:** capability use audited, references capability_id.

### Что новые ADRs (после spike обновления)

- **ADR-013** — Authorization model: capability-based with role bundles.
- **ADR-014** — Hierarchy: Org → Department → Project (3-level) [сейчас 2-level].
- **ADR-015** — AGENT/SERVICE scope conventions + parent-scope inheritance.
- **ADR-016** — Org policy mechanism (governing capabilities).
- **Update ADR-007** — RLS context: добавить `current_department`.
- **Update ADR-009** — Actor types: добавить `SERVICE`; CHECK constraint update.
- **Update ADR-010** — Audit: реference на capability_id.

### Что меняется в sub-issues (platform sub-issue #2..#8)

- **#2 Bootstrap:** schema includes `capabilities` table из старта.
- **#3 Identity:** capability provisioning при register / accept invitation.
- **#4 Tenants:** **переименовать «Multi-tenant hierarchy v0»** в «Multi-tenant hierarchy + access model»; добавить departments + capabilities.
- **#5 Audit:** `capability_id` reference в audit; policy enforcement audit.
- **#6 UI:** admin pages показывают roles (presentational); capability detail view — Phase 2.
- **#7 Observability:** capability check failures monitored.
- **#8 E2E:** verify per-project guest, AGENT scope, department isolation.

---

## Часть 9: Rejected альтернативы

### Pure RBAC + per-resource ACL on top

Большинство SaaS делают так. Получается **два независимых механизма**: RBAC для standard roles, per-resource ACL для guests / sharing. Каждый со своими checks, своим UI, своим audit. Дублирование, более сложная mental model.

### Pure capability (no role bundles)

Чисто semantically; но UX страдает: admin при создании user должен mint 7-10 capabilities вручную или из template. Bundle = template, идеологически identical.

### ACL only (resource → permitted actors)

Теряем actor-centric audit. Audit «что я мог?» сложно — надо джойнить ACL всех ресурсов с фильтром по actor.

### Attribute-Based Access Control (ABAC)

Generality (rules вроде «если user.dept = project.dept and user.clearance ≥ project.required...»). Слишком абстрактно для нашего контекста; rules тяжело отлаживать; performance.

---

## Заключение

**Hybrid (capabilities + role bundles)** — наиболее естественный fit для FASTSAAS:
- Покрывает все 5 use cases однозначно (UC-001..UC-007, UC-010).
- Familiar UX (роли) при гибком underlying механизме.
- Industry-standard direction (все production-grade IAM-системы конвергируют сюда).
- Growth-friendly: добавить custom roles = добавить bundle; добавить ad-hoc grant = create capability one-off.

**Следующий шаг:** добавить decision #11 в spike design.md с этим направлением, позже принять как ADR-013 после согласования.
