---
id: UC-001
title: Практик предоставляет клиенту read-only доступ к результатам результат проекта
level: Цель пользователя
priority: high
status: draft
created: 2026-05-01
author: Artem Konuchov (с Claude Code)
traces_to:
 related_features:
 - FE-CORE-2 # Multi-tenant Hierarchy
 - FE-CORE-1 # Actor-Centric Identity
 related_ar:
 - AR-7 # Multi-tenancy
 related_adr:
 - ADR-007 # Multi-tenant isolation
 - ADR-008 # Auth flow (magic-link для invitation)
 - ADR-009 # Actor model
 related_epic: the SaaS-core epic # Platform SaaS core
---

# UC-001: Практик предоставляет клиенту read-only доступ к результатам результат проекта

**Уровень:** Цель пользователя
**Приоритет:** Высокий
**Актор:** Practitioner — сотрудник консалтинговой фирмы
**Связанные требования:** FE-CORE-1, FE-CORE-2, AR-7

---

## Краткое описание

Практик завершил результат проекта целевого объекта в рамках проекта (как правило, один проект = одна результат проекта для одного клиента). Хочет предоставить **внешнему клиенту**, заказавшему результат проекта, доступ только на чтение к результатам — без права редактирования модельных параметров, входных данных или сценариев. Клиент **не является сотрудником** консалтинговой фирмы и обычно не имеет ранее аккаунта в FASTSAAS.

## Предусловия

- Практик аутентифицирован в FASTSAAS и имеет роль `member` или выше в своей организации.
- Проект существует в организации практик; практик — создатель проекта или имеет права на share.
- Расчёт по модели завершён, результаты сохранены и валидны.
- У клиента есть email-адрес.

## Постусловия (успех)

- Клиент получает email-приглашение со ссылкой для активации.
- При первом входе клиент создаёт аккаунт (или использует OAuth) — становится actor типа `HUMAN` без org-membership в организации практик.
- Клиент получает **per-project guest membership** только к этому одному проекту.
- Клиент видит результаты, не видит другие проекты практик, не видит данные других клиентов.
- Клиент не может изменять inputs, запускать новые расчёты, удалять scenarios.
- Все действия клиента (просмотр, экспорт) попадают в `audit_log` с `actor_id` = клиент-actor.

## Постусловия (неудача)

- Если приглашение не доставлено (SMTP error) — система уведомляет практик, помечает invitation `pending`.
- Если клиент не активирует приглашение в течение TTL (по умолчанию 7 дней) — invitation `expired`, практик может переотправить.
- При невалидном activation token — клиент видит generic "Приглашение недействительно".

---

## Основной поток (Happy Path)

| # | Актор (Практик) | Система |
|---|-----------------|---------|
| 1 | Открывает завершённый проект и инициирует «Поделиться с клиентом» | |
| 2 | | Показывает форму: email клиента, (опц.) имя, level доступа (read-only по умолчанию), TTL приглашения (7 дней по умолчанию) |
| 3 | Указывает email клиента и подтверждает | |
| 4 | | Создаёт invitation запись (`status=invited`, hash(token), expires_at); генерирует magic-link token (per ADR-008) |
| 5 | | Отправляет email с invitation link клиенту |
| 6 | | Подтверждает практик: «Приглашение отправлено [email]», статус в UI = `invited` |
| 7 | (Клиент в отдельной session) Открывает invitation link из email | |
| 8 | | Проверяет валидность token; либо создаёт нового actor (`HUMAN`), либо использует существующего (если email уже зарегистрирован) |
| 9 | | Создаёт guest-membership: `actor_id` → `project_id`, role = `guest_viewer` |
| 10 | | Помечает invitation как `accepted`; перенаправляет клиента в read-only view проекта |
| 11 | (Опционально) Практик видит в audit log активацию клиента | |

---

## Альтернативные потоки

### [A1] Клиент уже имеет FASTSAAS-аккаунт (другой email или тот же)

- На шаге 8: система обнаруживает existing user для email клиента.
- НЕ повышает права в чужой org; только добавляет per-project guest membership.
- Пропускает onboarding; перенаправляет сразу в шаг 10.

### [A2] Клиент — член другой FASTSAAS-организации (например, юрфирма от лица клиента)

- На шаге 8: email принадлежит члену другой org.
- Система добавляет cross-org guest-membership без затрагивания primary org клиента.
- Клиент при login в основной org видит свой обычный workspace; через UI «Shared with me» видит проекты-приглашения из других org.

### [A3] Практик отзывает доступ клиента

- На любом шаге после 5: практик в Settings проекта видит список guests, делает «Revoke».
- Система переводит guest-membership в `revoked`.
- При попытке клиента открыть проект — 404 (per ADR-007: не раскрываем существование).

### [A4] Практик приглашает нескольких людей со стороны клиента (например, accountant клиента + responsible manager)

- На шаге 3: вместо одного email — несколько (или CSV).
- Цикл шагов 4-6 для каждого; каждый получает свою guest-membership.

### [A5] Re-invite после expiration

- Если invitation `expired` (шаг 7 не выполнен в TTL): практик в UI видит status = `expired`, action = «Resend».
- Resend генерирует новый token, обнуляет TTL; старый token инвалидирован.

---

## Потоки исключений

### [E1] Email клиента невалиден

- На шаге 3: validation fails (формат, MX-record не существует).
- Inline-error на форме; практик исправляет.

### [E2] SMTP-доставка не удалась

- На шаге 5: SMTP error (недоступность, rate limit).
- Система сохраняет invitation как `pending_delivery`, retry через arq job (per ADR-005).
- Уведомляет практик inline + в notifications.

### [E3] Activation token expired при клике

- На шаге 7: token TTL истёк.
- Клиент видит: «Приглашение недействительно или истекло. Свяжитесь с [имя практик] для нового приглашения.»
- НЕ раскрывает существование проекта.

### [E4] Лимит guest-доступов на проект достигнут

- На шаге 4: org достиг quota (например, 10 guests на project).
- Сообщение практик: «Лимит guest-доступов достигнут. Удалите неактивных или повысьте план.»

### [E5] У практик недостаточно прав на share

- На шаге 1: практик не owner проекта и не имеет permission `project:share`.
- Кнопка «Поделиться» не показана; при попытке прямого API-вызова — 403.

---

## Бизнес-правила

- **BR-001:** Guest НИКОГДА не видит данные других клиентов / других проектов в org практик. Изоляция enforced на DB-уровне (RLS + per-project membership check).
- **BR-002:** Guest НЕ выполняет mutating operations (создать сценарий, запустить расчёт, изменить input).
- **BR-003:** Guest НЕ имеет доступа к org-level resources (members list, billing, settings, audit log org-level).
- **BR-004:** Все действия guest логируются в `audit_log` с `actor_id` = guest-actor (compliance + accountability).
- **BR-005:** Guest-membership имеет lifecycle: `invited` → `accepted` → (опц.) `revoked` / `expired`.
- **BR-006:** Inviter (практик) должен иметь permission `project:share` (по умолчанию — project owner или org admin).
- **BR-007:** Guest при попытке доступа к ресурсу вне scope получает 404, не 403 (consistency с ADR-007).
- **BR-008:** Invitation token хранится как `sha256(token)` в БД (per ADR-008).

---

## Открытые вопросы

- [ ] Может ли guest comment / задавать вопросы в проекте, или строго read-only? *Предложение для v1: read-only.*
- [ ] Может ли guest export результатов (PDF, XLSX)? *Предложение: да, это часть value proposition — клиент должен иметь свою копию отчёта.*
- [ ] Как guest узнаёт имя/контакт практик для вопросов? *Предложение: на проекте показывать "Created by [Practitioner Name]" с возможностью email-ссылки.*
- [ ] Когда проект помечен как `archived` — guest-доступ автоматически revoked или сохраняется? *Предложение: read-only сохраняется, write actions заблокированы.*
- [ ] Может ли guest поделиться доступом дальше (его коллега)? *Предложение для v1: нет; только практик может invite.*
- [ ] Per-project guest-membership — отдельная сущность от org-membership, или role `guest_viewer` в org-membership с `scope=specific_project_id`? *Дизайн-вопрос → ADR.*
- [ ] Self-service guest password reset / email change? *Предложение: yes, как обычный user.*
- [ ] Guest может удалить свой аккаунт? *GDPR-relevant — yes, anonymize в audit.*

---

## Связь с архитектурными решениями

- **ADR-007 (RLS):** guest membership = special row в RLS context; `SET LOCAL app.current_org` не подходит для guest — нужен `SET LOCAL app.current_project_grants` или другой механизм. **Это означает что наша RLS-модель не покрывает per-project guest scenario напрямую.**
- **ADR-008 (auth):** invitation использует ту же magic-link механику (TTL 7 дней per UC-001).
- **ADR-009 (actors):** guest = HUMAN actor; нет специального `actor_type=GUEST` — guest-status выражается через membership table, не через actor type.
- **ADR-010 (audit):** все guest-actions попадают в `audit_log` с `actor_id` указывающим на guest, `intent_metadata` отмечает «via_guest_invitation».
