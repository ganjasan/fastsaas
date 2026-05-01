---
id: UC-004
title: Пользователь использует AI Command Bar (Cmd+K) для inline-команд внутри web UI
level: Подфункция
priority: medium
status: draft
created: 2026-05-01
author: Artem Konuchov (с Claude Code)
traces_to:
 related_features:
 - FE-OPT-CMDBAR # AI Command Bar (FASTSAAS optional module)
 - FE-CORE-3 # Audit с intent_hash
 related_ar:
 - AR-4 # Declarative UI System
 related_adr:
 - ADR-009 # Actor model
 - ADR-010 # Audit log
 - ADR-012 # UI shadcn
 related_epic: post-#16 # Отдельный epic AI Command Bar
---

# UC-004: Пользователь использует AI Command Bar (Cmd+K) для inline-команд внутри web UI

**Уровень:** Подфункция
**Приоритет:** Средний (не для v1 SaaS-core; отдельный epic)
**Актор:** HUMAN actor (использует встроенный CMD+K, не отдельный AI-клиент)

**Связанные требования:** FE-OPT-CMDBAR (FASTSAAS), FE-CORE-3

---

## Краткое описание

Пользователь работает в FASTSAAS web UI. Открывает AI Command Bar (Cmd+K на Mac, Ctrl+K на Win/Linux). В свободной форме описывает действие — «создай новый проект для Office Tower AnalysisPipeline-A на Q3 2026» — LLM парсит intent → транслирует в API-вызовы → выполняет от имени пользователя. Это **HUMAN action**, не AGENT — отличается от UC-003 тем, что инициатор и исполнитель совпадают (HUMAN), AI только переводит natural language → API.

## Предусловия

- Пользователь аутентифицирован, в org/dept с правами на запрашиваемое действие.
- AI Command Bar feature module установлен и включён (FE-OPT-CMDBAR; в v1 SaaS-core отсутствует).
- LLM gateway (LiteLLM или прямое API к provider) настроен на org-уровне.
- Org admin не отключил CMD+K policy.

## Постусловия (успех)

- Запрошенное действие выполнено как обычное пользовательское действие.
- В `audit_log` действие помечено `intent_metadata.via=command_bar`, `intent_metadata.original_prompt=<user text>`.
- `actor_id` = HUMAN (не AGENT) — пользователь полностью отвечает за действие.

## Постусловия (неудача)

- Если LLM не смог parse intent → показывает «Не понял. Пример:...».
- Если действие требует прав которых у HUMAN нет → стандартный 403 / 404.

---

## Основной поток

| # | Актор (HUMAN) | Система |
|---|---------------|---------|
| 1 | Нажимает Cmd+K | |
| 2 | | Открывает overlay-modal с input field |
| 3 | Вводит «создай проект для Project Alpha, AnalysisPipeline-A, начало Q3 2026» | |
| 4 | | Отправляет prompt в LLM gateway (с context: current org, dept, available models, recent projects) |
| 5 | | LLM возвращает structured action: `{action: "create_project", params: {name: "Project Alpha", model: "analysis-pipeline-a", start_date: "2026-07-01"}}` |
| 6 | | Показывает HUMAN превью «Будет создан проект «Project Alpha» с моделью AnalysisPipeline-A и start_date Q3 2026. Confirm?» |
| 7 | HUMAN подтверждает (Enter) | |
| 8 | | Вызывает API endpoint как HUMAN; capability check проходит как обычно |
| 9 | | Создаёт project; audit row с `intent_metadata.via=command_bar` + `original_prompt` + `llm_interpretation` |
| 10 | | Закрывает modal, переходит на страницу нового проекта |

---

## Альтернативные потоки

### [A1] Multi-step intent

- На шаге 5: LLM понимает несколько действий в одном prompt: «создай проект, добавь buildings из CSV (uploaded), запусти AnalysisPipeline-A».
- Превью на шаге 6 показывает все 3 действия списком.
- HUMAN либо подтверждает все, либо разворачивает (uncheck) часть.
- Каждое действие создаёт свой audit row, все share один `intent_hash` (сессия CMD+K).

### [A2] Ambiguous intent — LLM спрашивает

- Если LLM неоднозначно интерпретирует: «start_date — какой Q3? Q3 2026 или Q3 2027?»
- Возвращает в Cmd+K dialog: «Уточни: какой год?»
- HUMAN отвечает; продолжается с шага 5.

### [A3] CMD+K используется в context конкретной страницы

- HUMAN на странице project «Project Alpha» открывает Cmd+K.
- Контекст автоматически прикрепляется: «текущий проект».
- Prompt «добавь optimistic scenario с +20% rents» интерпретируется в context этого проекта.

### [A4] Suggestion mode (без commit)

- HUMAN вводит «??» вместо команды.
- LLM показывает 3-5 saggested actions based on context: «Запустить AnalysisPipeline-A?», «Скопировать project?», «Поделиться с client?».

---

## Потоки исключений

### [E1] LLM не понял intent

- На шаге 5: LLM возвращает unparseable.
- Показывает HUMAN: «Не понял. Попробуй: «создай проект...» или «запусти модель...».»

### [E2] Действие требует прав, которых нет у HUMAN

- На шаге 8: capability check fails.
- Закрывает modal с message «Недостаточно прав».
- Audit: попытка зарегистрирована.

### [E3] LLM gateway недоступен

- На шаге 4: LiteLLM down.
- Cmd+K показывает «AI временно недоступен. Попробуй позже.»; UI продолжает работать.

### [E4] Org policy запрещает CMD+K destructive operations

- На шаге 5: LLM предложил `delete_project`.
- На шаге 6: превью НЕ показано; вместо этого «Cmd+K не разрешает destructive operations в этой org. Используй UI напрямую.»

---

## Бизнес-правила

- **BR-024:** CMD+K выполняет действия как HUMAN (не как AGENT) — `actor_type=HUMAN` в audit.
- **BR-025:** CMD+K не может выполнить действие, на которое HUMAN сам не имеет права (no privilege escalation).
- **BR-026:** Все CMD+K операции имеют `intent_metadata.via=command_bar` + `original_prompt`.
- **BR-027:** Multi-action sessions share один `intent_hash` для grouping.
- **BR-028:** Org-level policy может ограничивать CMD+K (например, запретить destructive).
- **BR-029:** Confirmation step обязателен перед выполнением (BR против accidental commits).

---

## Открытые вопросы

- [ ] Cmd+K в v1 SaaS-core или отдельный epic? *Предложение: отдельный epic, Phase 2-3.*
- [ ] LLM provider: LiteLLM gateway или прямые API? *Предложение: LiteLLM (FE-OPT-FINOPS из FASTSAAS).*
- [ ] Multi-step session UX: один prompt → несколько actions, или каждое action — separate prompt?
- [ ] Suggested actions caching: по user / по org / по global?

---

## Связь с архитектурными решениями

- **Не часть v1 SaaS-core (#16).** Включается отдельным epic «AI Command Bar» — Phase 2-3.
- **ADR-010 (audit):** `intent_metadata.via=command_bar` + `original_prompt` достаточно для tracking (схема не меняется).
- **ADR-009 (actors):** не требует AGENT actors; всё под HUMAN identity.
- **Различие с UC-003:** UC-003 — AGENT действует от имени HUMAN; UC-004 — HUMAN использует AI как UI-обёртку. Audit tracking разный.
