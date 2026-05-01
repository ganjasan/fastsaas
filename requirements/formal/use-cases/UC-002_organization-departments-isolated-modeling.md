---
id: UC-002
title: Подразделение крупной организации использует FASTSAAS для изолированного моделирования
level: Цель пользователя (множественная)
priority: high
status: draft
created: 2026-05-01
author: Artem Konuchov (с Claude Code)
traces_to:
 related_features:
 - FE-CORE-2 # Multi-tenant Hierarchy
 related_ar:
 - AR-7 # Multi-tenancy
 related_adr:
 - ADR-007 # Multi-tenant isolation
 - ADR-009 # Actor model
 related_stakeholders:
 - Globex # Большой клиент с множеством департаментов
 - Acme Consulting # Меньший клиент, может вырасти до multi-team
 related_epic: the SaaS-core epic # Platform SaaS core
---

# UC-002: Подразделение крупной организации использует FASTSAAS для изолированного моделирования

**Уровень:** Цель пользователя (множественная — три актора)
**Приоритет:** Высокий
**Акторы:**
- **Org Admin** (HQ-уровень: ИТ-директор / FASTSAAS-внедряющий со стороны клиента)
- **Department Lead** (например, лид Acquisitions team)
- **Department Member** (analyst в Asset Management team)

**Связанные требования:** FE-CORE-2, AR-7

---

## Краткое описание

Крупная компания (например, Globex с large enterprise portfolio) имеет несколько подразделений — Acquisitions, Asset Management, Risk, Reporting, Tax — каждое использует FASTSAAS для своего типа моделирования (AnalysisPipeline-C для acquisitions, AnalysisPipeline-B для asset management, и т.д.). Подразделения работают с разными типами объектов и сценариев. **Данные одного подразделения не должны быть видны другим** — даже внутри одной организации. При этом HQ-уровень нуждается в aggregated reporting (для billing, compliance, capacity planning).

## Предусловия

- Организация существует в FASTSAAS (например, «Globex»).
- Org Admin аутентифицирован, имеет роль `owner` или `admin`.
- FASTSAAS поддерживает понятие **Department** (Team / Sub-organization) — отдельная сущность в hierarchy с собственными members и проектами.

## Постусловия (успех)

- Org Admin создал N подразделений с уникальными именами.
- Department Members видят только проекты своего подразделения; могут создавать/редактировать в его рамках.
- Department Leads видят и управляют только проектами своего подразделения.
- Org Admin (HQ) видит aggregated metrics по всем подразделениям (количество проектов, model executions, storage usage), **но не операционные данные** (входы моделей, результаты).
- Cross-department sharing возможен явно через invitation/transfer; не происходит по умолчанию.

## Постусловия (неудача)

- Если member пытается просмотреть данные другого department — получает 404 (per ADR-007, не раскрываем существование).
- Если Department Lead пытается invite в другой department — 403.

---

## Основной поток (Happy Path) — Setup & Day-to-Day

### Setup-фаза (Org Admin)

| # | Актор (Org Admin) | Система |
|---|-------------------|---------|
| 1 | Принимает org-invitation; либо создаёт новую организацию | |
| 2 | | Создаёт organisation, admin = owner |
| 3 | Открывает Settings → Departments → New Department | |
| 4 | | Показывает форму: название, описание |
| 5 | Создаёт department «Acquisitions» (повторяется для каждого подразделения) | |
| 6 | | Создаёт department-сущность под org; admin = creator (либо назначает другого как Department Lead) |
| 7 | Приглашает Department Lead через email (с указанием department) | |
| 8 | | Создаёт invitation; при принятии — adds actor к org с role `member`, к department с role `dept_lead` |

### Day-to-day (Department Lead)

| # | Актор (Department Lead) | Система |
|---|--------------------------|---------|
| 9 | Логинится; видит только свой department (Acquisitions) в навигации | |
| 10 | | Перечисляет projects в Acquisitions; не показывает projects других departments |
| 11 | Приглашает Department Members в Acquisitions (через email) | |
| 12 | | Каждый member получает org-membership (`role=member`) + dept-membership (`role=dept_member`) |
| 13 | Создаёт project (например, «Project Alpha — Acquisition Q3 2026») | |
| 14 | | Project создаётся с `department_id=Acquisitions`; visible только members этого department |

### Day-to-day (Department Member)

| # | Актор (Department Member) | Система |
|---|----------------------------|---------|
| 15 | Логинится; видит project list своего department | |
| 16 | Открывает project, запускает модель (AnalysisPipeline-C) | |
| 17 | | Выполняет расчёт; результаты сохраняются в этом project |
| 18 | (Гипотетически) Member из Asset Mgmt пытается открыть Acquisitions-project через прямой URL | |
| 19 | | Возвращает 404; ничего не раскрывает |

### HQ Reporting (Org Admin периодически)

| # | Актор (Org Admin) | Система |
|---|-------------------|---------|
| 20 | Открывает Org Reports / Usage Dashboard | |
| 21 | | Показывает aggregated metrics per department: project counts, model executions, storage; НЕ показывает project content |

---

## Альтернативные потоки

### [A1] User состоит в нескольких departments

- На шаге 12: actor добавлен в Acquisitions и в Risk.
- При login видит navigation: «Acquisitions / Risk» как переключатель (org-switcher эквивалент для departments).
- Project list scoped к выбранному department.
- В audit_log каждое действие связано с активным department-контекстом.

### [A2] Cross-department transfer проекта

- Department Lead Acquisitions делает «Transfer to another department» на конкретном project.
- Система запрашивает подтверждение target department lead'а.
- При acceptance: `project_id` остаётся, `department_id` меняется; access list обновляется автоматически.

### [A3] Cross-department guest collaboration (single project)

- Acquisitions хочет показать результат конкретного project отделу Risk на review.
- Department Lead Acquisitions добавляет user из Risk как `external_viewer` к этому project (механизм аналогичен UC-001 guest, но cross-department, не cross-org).
- User остаётся в своём primary department (Risk); получает per-project read-access к Acquisitions-project.

### [A4] Department deletion

- Org Admin удаляет department.
- Если в department есть active projects — система блокирует, требует:
 - либо transfer projects в другой department,
 - либо явный cascade-archive (soft-delete projects + dept).
- audit_log сохраняется для всех затронутых entities.

### [A5] HQ Compliance audit cross-departmental

- Compliance Officer (специальная роль на org-level) запрашивает audit log нескольких departments.
- Получает union audit-rows с filter по date/action; не получает project content.
- Логируется тот факт что compliance officer выполнил cross-dept audit.

### [A6] Department needs own billing / quota

- Asset Management имеет собственный budget и должен иметь quota на model executions.
- Org Admin устанавливает per-department quotas в Settings → Departments → Acquisitions → Quotas.
- При превышении dept quota — execution блокируется, не affecting другие departments.

---

## Потоки исключений

### [E1] Department name conflict

- На шаге 5: имя «Acquisitions» уже существует в этой org.
- Inline error, требует уникальное имя.

### [E2] Member пытается создать project без department

- На шаге 13: member состоит в нескольких departments, не выбрал target.
- Система не позволяет «orphan» project (org-level project без department).
- Требует выбор department из dropdown.

### [E3] Department Lead инвайтит member, который уже member другой org

- На шаге 11: email уже зарегистрирован в другой FASTSAAS-org.
- Создаёт linked actor (тот же email, second org-membership в этой org); existing primary org user не меняется.

### [E4] Org Admin удаляет department с активными projects без transfer

- На шаге A4: cascade без явного подтверждения.
- Запрос подтверждения с full warning (число projects, scenarios, exec history); requires text confirmation department name.

### [E5] User теряет membership в единственном department

- Если у user был один department, и его оттуда remove (Department Lead removed member).
- User остаётся org member, но без department-context — не может открывать projects.
- UI показывает «Вы пока не состоите ни в одном department; обратитесь к администратору».

---

## Бизнес-правила

- **BR-007:** Каждый project обязан принадлежать ровно к одному department в рамках org.
- **BR-008:** Member видит только данные departments, в которых он состоит; cross-department access требует явного действия (UC-001 guest pattern или transfer).
- **BR-009:** Department-level isolation enforced на DB-уровне через расширение RLS-context: `SET LOCAL app.current_department = '<uuid>'` дополнительно к `app.current_org`.
- **BR-010:** Org Admin (`owner`/`admin`) видит aggregated metadata всех departments, но не их операционные данные. Operational access требует явного добавления в department как member или dept_lead.
- **BR-011:** Department Lead имеет полные права в своём department (invite/remove dept members, manage projects), но НЕ может invite/remove org-level members; для этого требуется org admin.
- **BR-012:** Удаление org → каскад на departments (soft-delete per ADR-006); audit_log сохраняется во всех слоях.
- **BR-013:** Department deletion требует явного transfer projects или cascade-archive; никогда — silent data loss.
- **BR-014:** HQ Compliance role (если введена) — это новый role beyond standard RBAC: read-only audit_log cross-department, без доступа к operational data.

---

## Открытые вопросы

- [ ] **Department — это новая сущность в hierarchy, или просто tag/group поверх org?** *Анализ показывает: для real isolation (RLS) нужна отдельная сущность.*
- [ ] **Может ли department иметь sub-departments (рекурсивная иерархия)?** *Предложение для v1: нет, плоский список под org.*
- [ ] **Может ли project принадлежать нескольким departments (shared)?** *Предложение: нет, строго один; cross-dept share — через guest-pattern UC-001.*
- [ ] **Cross-department billing:** один счёт на org или per-department с показом share? *Предложение: один счёт на org с usage breakdown per department.*
- [ ] **Department-level quotas (max projects, max model executions):** в v1 или Phase 2? *Предложение: foundation готов в v1, enforcement — Phase 2.*
- [ ] **HQ-level compliance role** — это новый role beyond owner/admin/member/viewer? *Предложение: yes — `compliance_officer` org-level role с read-only audit access cross-dept.*
- [ ] **UI department-switcher** vs concurrent view нескольких departments? *Предложение: switcher в v1; возможно concurrent in future.*
- [ ] **Что делать с org, у которой только один department (типичный SMB)?** *Предложение: department обязателен, но при создании org система автоматически создаёт default department «Main».*
- [ ] **Department Lead vs admin различие в правах:** должны ли они различаться, или dept_lead = department-scoped admin? *Предложение: dept_lead = department-scoped admin (полные права в dept).*
- [ ] **Может ли user быть org admin, но не быть в department?** *Предложение: да; admin видит aggregated metrics, не operational data, как BR-010.*
- [ ] **Department audit_log isolation:** Department Lead видит audit только своего dept? *Предложение: yes; org admin видит cross-dept aggregated; compliance видит cross-dept detailed.*
- [ ] **Когда применима «Default department»** vs requiring explicit dept setup? *Возможные answer: для small orgs (< 5 users) skip dept setup, всё в Main; для bigger — explicit.*

---

## Связь с архитектурными решениями

Этот UC значительно **расширяет hierarchy и access model**, что не было полностью покрыто в spike #17:

- **Hierarchy `Org → Project`** из spike недостаточна; нужна **`Org → Department → Project`** (3-level), что соответствует FASTSAAS FE-CORE-2 в более полной форме.
- **ADR-007 (RLS)** нужно расширить: `SET LOCAL app.current_org` + `SET LOCAL app.current_department`.
- **Permission model** требует понятия department-scoped roles (`dept_lead`, `dept_member`) дополнительно к org-scoped (`owner`, `admin`, `member`, `viewer`).
- **Новый actor concept (возможно):** Compliance Officer — org-level role с особым audit-доступом.
- **Schema:**
 ```
 organisations (existing per ADR-006/007)
 ├── departments (NEW)
 │ ├── department_members (NEW: actor_id, department_id, role)
 │ └── projects (existing, NOW carries department_id)
 └── organisation_members (existing: actor_id, org_id, role)
 ```

Эти изменения — материал для нового decision (#11 в spike, или отдельного ADR).
