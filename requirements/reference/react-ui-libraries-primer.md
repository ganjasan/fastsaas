---
title: "React UI Libraries — primer для выбора component library"
created: 2026-05-01
status: reference
purpose: "Объяснить ландшафт component libraries для решения #10 в spike platform-saas-core-architecture"
related:
 - "[[../decisions/ADR-004_frontend-stack]]"
 - "[[../../openspec/changes/platform-saas-core-architecture-spike/design.md|design.md decision #10]]"
---

# React UI Libraries — что это всё такое

Документ-ликбез: что такое «component library», какие подходы существуют, чем shadcn отличается от Tremor, и какой выбор имеет смысл для FASTSAAS.

---

## Часть 1: Что такое «component library»

Когда строишь web-интерфейс, у тебя есть строительные блоки: кнопки, поля ввода, выпадающие списки, диалоги, таблицы, карточки. Их можно:

1. **Написать с нуля** — каждую кнопку, каждое поле. Долго, много багов, accessibility (поддержка скринридеров и клавиатуры) — отдельная адова работа.
2. **Использовать готовую библиотеку** — кто-то уже написал и оттестировал. Импортируешь и используешь.

«Component library» — это набор готовых React-компонентов: `<Button>`, `<Dialog>`, `<Select>`, `<Table>`, и т.д.

### Пример без библиотеки

```tsx
// Самописная кнопка — простая, но без accessibility, hover, focus, disabled states
function MyButton({ onClick, children }) {
 return <button onClick={onClick} style={{ padding: '8px 16px' }}>{children}</button>;
}
```

### Пример с библиотекой

```tsx
import { Button } from "@/components/ui/button"; // shadcn

<Button variant="primary" size="md" disabled={loading} onClick={save}>
 Save
</Button>
```

Получаешь: правильный hover, focus, disabled state, screen-reader announcement, клавиатурная навигация — всё это работает из коробки.

---

## Часть 2: Два подхода — npm-package vs copy-paste

Есть два философских подхода к component libraries.

### Подход А: npm package

Классика. Устанавливаешь библиотеку как зависимость, импортируешь компоненты.

```bash
npm install @mui/material # Material UI
```

```tsx
import { Button } from '@mui/material';
<Button variant="contained">Save</Button>
```

**Плюсы:**
- Установил один раз, обновляешь через `npm update`.
- Bug-fixes и новые фичи приходят автоматически.

**Минусы:**
- **Не можешь нормально кастомизировать.** Если хочется чтобы кнопка была чуть другая — приходится бороться с библиотекой через `theme prop`, `styled-component overrides`, и т.п. Часто проще переписать с нуля.
- **Black box.** Открыл компонент в DevTools — увидел `<MuiButton__StyledRoot-sc-1q0a3z2>...</...>` и не понимаешь, что там внутри.
- **AI-агент не может удобно с этим работать** — Claude/Cursor видят только импорт, не реализацию.

**Примеры:** Material UI, Chakra UI, Mantine, Ant Design, Bootstrap.

### Подход Б: copy-paste (новая школа)

Не библиотека, а **CLI-инструмент**, который копирует исходник компонента **в твой репозиторий**. Компонент становится частью твоего кода.

```bash
npx shadcn-ui@latest add button # копирует button.tsx в src/components/ui/
```

После этого:
- В `src/components/ui/button.tsx` лежит ~80 строк кода — обычный React-компонент.
- Можешь его модифицировать как хочешь.
- Можешь удалить часть фич, добавить свои.

```tsx
// src/components/ui/button.tsx — это твой код, ты владелец
import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/lib/utils"

const buttonVariants = cva(
 "inline-flex items-center justify-center rounded-md text-sm font-medium...",
 {
 variants: {
 variant: { default: "...", destructive: "...", outline: "..." },
 size: { sm: "h-8", md: "h-10", lg: "h-12" }
 }
 }
)

export function Button({ className, variant, size,...props }) {
 return <button className={cn(buttonVariants({ variant, size }), className)} {...props} />
}
```

**Плюсы:**
- Полный контроль — твой код, твоя ответственность.
- Прозрачно — видишь как работает каждый компонент.
- AI-агент видит код в репо и может его изменять/расширять.
- Нет «версии библиотеки» — нечего обновлять.

**Минусы:**
- Bug-fix в исходной библиотеке не приходит автоматически — надо вручную смотреть changelog и переписывать.
- Если компонентов много — много кода в твоём репо.

**Это та модель, которую популяризировал shadcn (с 2023).** До этого все были на npm-package model.

---

## Часть 3: Откуда берётся accessibility и поведение?

Если shadcn — это просто copy-paste, что обеспечивает что кнопка корректно работает с клавиатурой и screen reader?

Ответ: **Radix UI** (и аналоги типа Headless UI).

**Radix UI** — это «headless» библиотека. Она даёт **только поведение и accessibility**, без визуального дизайна.

```tsx
import * as Dialog from '@radix-ui/react-dialog';

<Dialog.Root>
 <Dialog.Trigger>Open</Dialog.Trigger>
 <Dialog.Content>...</Dialog.Content>
</Dialog.Root>
// ↑ Никакого CSS, никакого внешнего вида. Только логика:
// - открывается по клику на Trigger
// - закрывается по Esc
// - focus trap внутри Content
// - aria-attributes для screen readers
```

shadcn = **Radix UI (поведение) + Tailwind CSS (стили) + структура файлов в твоём репо**.

```
shadcn/ui = "вот тебе button.tsx, который под капотом использует Radix
 и одевает его в Tailwind-классы для красивого вида"
```

Ссылка: https://www.radix-ui.com/

---

## Часть 4: Конкретные библиотеки (с визуальными примерами)

### shadcn/ui — индустриальный стандарт

- **Сайт:** https://ui.shadcn.com/
- **Каталог компонентов:** https://ui.shadcn.com/docs/components/button
- **Примеры (готовые экраны):** https://ui.shadcn.com/examples
- **GitHub:** https://github.com/shadcn-ui/ui (~76K stars)

**Что это:** ~50 готовых компонентов на Radix UI + Tailwind, copy-paste model. Создал @shadcn (Брайан Лоувин из Vercel), стало стандартом 2024-26 для React-проектов.

**Как выглядит:**
- Эстетика: чистый минимализм, как у Vercel/Linear.
- Поддержка dark mode из коробки.
- Готовые «Examples» — целые экраны (Dashboard, Cards, Authentication, Mail) можно скопировать.

**Реальные продукты на shadcn:** Vercel dashboard, Resend, Cal.com, Supabase dashboard.

**Скриншоты примеров:** https://ui.shadcn.com/examples/dashboard ← открой эту ссылку, это ровно то, как будет выглядеть FASTSAAS-платформа.

---

### Tremor — для дашбордов и графиков

- **Сайт:** https://tremor.so/
- **Компоненты:** https://tremor.so/docs/getting-started/installation
- **Примеры:** https://tremor.so/docs/visualizations/area-chart
- **GitHub:** https://github.com/tremorlabs/tremor (~16K stars)

**Что это:** Специализированная библиотека на Tailwind для **dashboard-первых приложений**. Сильна в:
- Charts: BarChart, LineChart, AreaChart, ScatterPlot, DonutChart.
- KPI cards: «Revenue 2.4M ↑ 12%».
- Trackers, sparklines, числовая визуализация.

**Чем отличается от shadcn:**
- shadcn = general-purpose UI (кнопки, формы, модалки).
- Tremor = **dashboard-специализация** (charts, метрики).
- **Они комплементарны.** shadcn для общего UI, Tremor для charts (когда понадобятся).

**Реальные продукты на Tremor:** Vercel Analytics, Resend dashboard.

**Скриншот:** https://blocks.tremor.so/blocks/dashboard ← дашборды с графиками.

---

### Park UI — альтернатива

- **Сайт:** https://park-ui.com/
- **Каталог:** https://park-ui.com/docs/react/components/accordion
- **GitHub:** https://github.com/cschroeter/park-ui (~5K stars)

**Что это:** Аналог shadcn, но **на Ark UI вместо Radix UI**. Ark UI — более новый headless library от команды Chakra.

**Почему НЕ выбираем для FASTSAAS:** мы committed к Radix UI (per ADR-004). Park UI значит переключение foundation, что не оправдано.

---

### Catalyst — платный, от Tailwind team

- **Сайт:** https://catalyst.tailwindui.com/
- **Цена:** $299 разовая покупка (часть Tailwind UI bundle)
- **Создатели:** Adam Wathan (создатель Tailwind) и его команда

**Что это:** Платный набор премиум-компонентов от создателей Tailwind. Качество выше shadcn (визуально), copy-paste model.

**Почему НЕ выбираем:**
- Платно ($299 — небольшие деньги, но lock-in).
- Лицензия запрещает re-distribution — если когда-то откроем FASTSAAS в open-source, надо переписывать.
- shadcn покрывает 95% потребностей бесплатно.

---

## Часть 5: Tailwind v3 vs v4 — это важно

Tailwind CSS — фреймворк для стилизации, который мы используем (per ADR-004). У него две версии в живой природе:

| | Tailwind v3 | Tailwind v4 |
|--|------------|------------|
| Релиз | 2021 (стабильный 4 года) | январь 2025 (стабильный) |
| Конфиг | `tailwind.config.js` (JavaScript) | CSS-first (через `@theme` директиву) |
| Скорость билда | Хорошая | **5-10× быстрее** |
| Совместимость shadcn | ✅ 100% | ✅ покрытие 95%+ к 2026 |
| Theme variables | Через JS config | Через CSS variables — чище |

**Visual difference:** в v4 много новых color palettes (P3 wide-gamut), но визуально всё похоже на v3.

**Рекомендация:** Tailwind v4 — она уже стабильна, заметно быстрее в dev, чище в коде. Шанс упереться в shadcn-несовместимость минимальный.

Ссылка: https://tailwindcss.com/blog/tailwindcss-v4

---

## Часть 6: Storybook и Ladle — визуальный каталог

Когда у тебя 30+ компонентов, нужен «каталог» — страница, где можно увидеть все компоненты, их варианты, состояния. Это инструмент для дизайнеров и разработчиков.

### Storybook — индустриальный стандарт

- **Сайт:** https://storybook.js.org/
- **Что это:** Отдельное приложение, которое показывает каждый компонент в изоляции.
- **Минусы:** Тяжёлый (50MB установка), медленный startup, отдельный build pipeline.

**Скриншот примера:** https://storybook.js.org/docs/get-started/whats-a-story (внизу есть пример интерфейса).

### Ladle — лёгкая альтернатива

- **Сайт:** https://ladle.dev/
- **Создатель:** Вadima Kharitonov (Vercel, бывший Storybook contributor)
- **Что это:** «Storybook для Vite», в 10× меньше и быстрее.

**Для FASTSAAS:** не нужен в v1. Все базовые компоненты shadcn документированы на ui.shadcn.com — каталог уже есть, не надо повторять.

**Когда понадобится:** когда добавим FASTSAAS-specific компоненты (визуализация Scenario, Property card, Lease editor) — тогда Ladle.

---

## Часть 7: Что я рекомендую для FASTSAAS

### Component library: **shadcn/ui**

Причины:
1. **Это стандарт.** 76K stars, в каждом туториале React 2025-26.
2. **AI-агенты (Claude, Cursor) знают shadcn идеально** — реализуют любой UI без боя.
3. **Copy-paste model** даёт нам контроль над каждым компонентом.
4. **MIT лицензия** — public-ready friendly, если когда-то откроем.
5. **Совместимо с нашим стэком** (Radix UI + Tailwind + CVA per ADR-004).

### Charts: **Tremor — добавим когда понадобится**

В v1 SaaS-core (epic #16) charts не нужны. В epic #2 (Orchestrator core, визуализация модельных результатов) — добавим Tremor, не переделывая существующее.

### Tailwind: **v4**

Стабилен с января 2025, к маю 2026 уже год production-use. Быстрее, чище, theme через CSS variables.

### Storybook/Ladle: **отложить в backlog**

shadcn компоненты задокументированы на ui.shadcn.com. Свой каталог понадобится когда появятся FASTSAAS-specific компоненты.

### Конкретный набор компонентов для bootstrap (#1 в platform)

```bash
npx shadcn-ui@latest add \
 button input label form select dialog sheet toast \
 card badge dropdown-menu avatar separator skeleton table
```

13 компонентов. Покрывают: формы (login, registration, settings), layout (sidebar, dialog, sheet), data display (cards, tables, badges), feedback (toast, skeleton).

---

## Резюме

```
FASTSAAS frontend stack:
├── React 18 + TypeScript + Vite [ADR-004]
├── TanStack Router + TanStack Query [ADR-004]
├── Radix UI (headless primitives) [ADR-004]
├── Tailwind CSS v4 [ADR-004]
├── shadcn/ui — component library [этот primer → решение #10]
└── (позже) Tremor для charts [когда дойдём в epic #2]
```

**Что значит "shadcn/ui" в одной фразе:**
> Готовые React-компоненты на Radix UI + Tailwind, скопированные в твой репозиторий через CLI, с контролем над каждой строчкой кода.

---

## Полезные ссылки для самостоятельного знакомства

| Что | Ссылка |
|-----|--------|
| Главная shadcn | https://ui.shadcn.com/ |
| Каталог компонентов shadcn | https://ui.shadcn.com/docs/components/button |
| Примеры готовых экранов на shadcn | https://ui.shadcn.com/examples |
| Demo dashboard на shadcn (≈как будет FASTSAAS) | https://ui.shadcn.com/examples/dashboard |
| Radix UI — что под капотом | https://www.radix-ui.com/primitives |
| Tailwind CSS v4 announcement | https://tailwindcss.com/blog/tailwindcss-v4 |
| Tremor (для будущих charts) | https://tremor.so/ |
| Ladle (когда будет нужен Storybook-аналог) | https://ladle.dev/ |
| shadcn vs alternatives — comparison post | https://www.shadcndesign.com/blog/why-shadcn-changed-everything |

---

# Часть 8: shadcn — это не библиотека, это **экосистема и движение**

Когда говорят «shadcn», подразумевают сразу 5 вещей:

1. **Человек** — Brian Lovin (shadcn — его никнейм), DevRel в Vercel.
2. **Философия** — «Open Code» (об этом ниже).
3. **CLI-инструмент** — `npx shadcn add...` который копирует **что угодно** из любого registry.
4. **Канонический registry** — `ui.shadcn.com` с компонентами, блоками, темами, графиками.
5. **Целая экосистема** — десятки third-party libraries построены на той же модели и совместимы с тем же CLI.

Когда понимаешь эти 5 вещей — становится ясно, почему shadcn «больше чем библиотека».

---

## 8.1 Философия «Open Code»

shadcn в 2024 году опубликовал manifesto:

> «Frontend developers spent the last decade hiding code behind abstractions. Components became opaque packages. UI became something you configured, not something you owned.
>
> **Open Code is the antidote.** Your UI lives in your codebase. You read it, change it, refactor it. AI sees it and understands it. There's no library to upgrade — your code IS the library.»

Это не просто маркетинг. Это **смена парадигмы**:

| Старая парадигма (npm package) | Open Code (shadcn-style) |
|--------------------------------|--------------------------|
| `import { Button } from '@library/x'` | `import { Button } from '@/components/ui/button'` |
| Black box — не знаешь как работает | Whitebox — твой код в твоём репо |
| Кастомизация = борьба с библиотекой | Кастомизация = редактирование файла |
| AI-агент видит только импорт | AI-агент видит реализацию |
| Upgrade = боль (breaking changes) | Upgrade = вручную смотришь diff |
| Библиотека контролирует тебя | Ты контролируешь свой UI |

**Ссылка:** https://ui.shadcn.com/docs (раздел Philosophy)

Эта философия — **прямой ответ AI-эре**. AI-агентам нужно видеть код чтобы его править. Закрытый npm package = AI бессилен. Открытый код в репо = AI может читать, изменять, расширять.

Вот почему shadcn так быстро стал стандартом — он совпал с моментом, когда Claude/Cursor стали основным инструментом разработчика.

---

## 8.2 CLI как мета-инструмент

`shadcn` CLI — это **не «установщик компонентов»**, это **универсальный распаковщик** того, что ему говорят установить.

```bash
# Компонент
npx shadcn add button

# Блок (целая секция страницы)
npx shadcn add login-01

# Тему
npx shadcn add theme-zinc

# График
npx shadcn add chart-bar-01

# Любой URL (custom registry)
npx shadcn add https://my-company.com/registry/our-button.json

# Полный template (приложение целиком)
npx shadcn add https://example.com/saas-template.json
```

**CLI выполняет операцию по JSON-манифесту:**
1. Загружает файлы.
2. Кладёт в правильные места твоего репо.
3. Устанавливает npm-зависимости (Radix UI, и т.п.).
4. Обновляет `tailwind.config.js`, если нужно.
5. Решает конфликты (если файл уже существует — спрашивает).

**Это инфраструктура,** а не библиотека. Над ней люди строят свои наборы компонентов.

**Документация:** https://ui.shadcn.com/docs/cli

---

## 8.3 Registry — формат, который победил

«Registry» в мире shadcn — это просто **JSON-манифест**, описывающий что и куда положить.

### Пример registry-item

```json
{
 "name": "button",
 "type": "registry:ui",
 "dependencies": ["@radix-ui/react-slot"],
 "devDependencies": [],
 "registryDependencies": [],
 "files": [
 {
 "path": "ui/button.tsx",
 "content": "...весь код button.tsx...",
 "type": "registry:ui"
 }
 ],
 "tailwind": {
 "config": {
 "theme": {
 "extend": { "colors": { "primary": "..." } }
 }
 }
 }
}
```

CLI читает это и копирует файлы.

### Что важно

**Любой может хостить свой registry** — это просто статический JSON-файл. Поэтому:

- Vercel хостит canonical registry на ui.shadcn.com.
- Aceternity UI хостит свой.
- Magic UI хостит свой.
- **Твоя компания может хостить свой** внутренний design system.

```bash
# Внутренний registry компании
npx shadcn add https://design.fastsaas.com/registry/property-card.json
```

Это значит **FASTSAAS может собрать свой design system** для специфичных компонентов (PropertyCard, ScenarioComparison, LeaseEditor) и распространять их через тот же CLI. Огромная мощь.

**Документация registry:** https://ui.shadcn.com/docs/registry

---

## 8.4 Blocks — целые секции страниц

«Component» = одна Button.
«Block» = целая Login-страница, Sidebar, Hero-секция.

Блоки — это **готовые куски UI**, которые копируются в репо как обычные компоненты, но представляют **целый user-facing элемент**.

### Каталог блоков

https://ui.shadcn.com/blocks

| Категория | Примеры |
|-----------|---------|
| Authentication | login forms, signup, magic-link, OAuth pages |
| Dashboard | full dashboards с метриками и графиками |
| Sidebar | 17 разных вариантов sidebar layout |
| Calendar | full calendar pages |
| Mail | inbox / list / reader как в Linear |
| Settings | settings pages с табами |

**Пример:** `npx shadcn add sidebar-07` копирует **полную dashboard layout** с sidebar в твой репо. После этого у тебя:

```
src/components/sidebar-07.tsx (главная компонента)
src/components/nav-main.tsx (sub-component)
src/components/nav-projects.tsx (sub-component)
src/components/nav-secondary.tsx
src/components/team-switcher.tsx
src/components/user-nav.tsx
```

И весь это работает. Тебе остаётся только заменить moc-данные на реальные.

**Это game-changer для скорости.** Login страница в FASTSAAS = `npx shadcn add login-04` + замена API-вызовов = 30 минут вместо дня.

---

## 8.5 Theme system — `theme.json` + CSS variables

shadcn использует **CSS variables** для темы (а не Tailwind config). Это значит:

```css
/* src/styles/theme.css */
:root {
 --background: 0 0% 100%;
 --foreground: 222.2 84% 4.9%;
 --primary: 222.2 47.4% 11.2%;
 --primary-foreground: 210 40% 98%;
 /*... */
}.dark {
 --background: 222.2 84% 4.9%;
 --foreground: 210 40% 98%;
 /*... */
}
```

Можно менять тему **на лету** (без билда), просто переключая CSS-переменные.

### Каталог тем

https://ui.shadcn.com/themes

Можно выбрать стиль (Zinc / Slate / Neutral / Stone / Gray / Red / Rose / Orange / Green / Blue / Yellow / Violet) и видеть **live preview всего dashboard** в этой палитре.

### Theme editor (третья сторона)

https://tweakcn.com/ — визуальный редактор тем shadcn. Двигаешь слайдеры → видишь как меняется UI → экспортируешь готовый `theme.css`.

Это значит **brand-кастомизация FASTSAAS** = 30 минут в tweakcn вместо неделя дизайнера.

---

## 8.6 Charts — shadcn теперь умеет графики

С 2024 shadcn **встроил charts** в каноничный registry:

https://ui.shadcn.com/charts

Под капотом — Recharts (популярная chart library), но завёрнут в shadcn-style API.

### Что есть

- **Bar charts** (single, stacked, mixed)
- **Line charts** (single, multiple, gradient, custom dots)
- **Area charts** (linear, step, gradient)
- **Pie charts** (с labels, donut, interactive)
- **Radar / Radial / Scatter**
- **Tooltips и legends** в shadcn-стиле

```bash
npx shadcn add chart-bar-01
```

→ копирует готовый chart с моковыми данными и UI обёрткой.

### Это меняет наш план

Раньше я говорил «Tremor для charts когда понадобится» — но теперь, **когда в shadcn есть свои charts**, Tremor может вообще не понадобиться.

```
Старый план: shadcn (UI) + Tremor (charts когда дойдём)
Новый план: shadcn (UI + charts) — всё из одного registry
```

Tremor имеет смысл только если нужна очень специфическая dashboard-визуализация (heatmap, tracker bars, sparklines из коробки). Для большинства случаев **shadcn-charts достаточно**.

---

## 8.7 Экосистема — десятки совместимых registries

Множество third-party libraries следуют shadcn-формату registry. CLI работает с ними всеми.

### Aceternity UI — анимации и эффекты

https://ui.aceternity.com/

Сложные анимированные компоненты: parallax, gradient borders, animated cards, scroll triggers, interactive backgrounds. Всё совместимо с shadcn CLI.

```bash
npx shadcn@latest add https://ui.aceternity.com/registry/3d-card.json
```

### Magic UI — визуальные эффекты

https://magicui.design/

Аналог Aceternity, фокус на marketing landing pages. Бегущие линии, animated lists, particle backgrounds.

### Origin UI — базовые компоненты с вариантами

https://originui.com/

Расширенные варианты shadcn-компонентов: 50+ кнопок, 40+ форм, 100+ inputs.

### 21st.dev — marketplace компонентов

https://21st.dev/

Сайт-каталог где разработчики публикуют свои shadcn-совместимые компоненты. Можно просматривать, искать, копировать в свой проект через CLI. Что-то вроде GitHub Gist для UI компонентов.

### shadcn для других фреймворков

- **shadcn/vue** — https://www.shadcn-vue.com/
- **shadcn/svelte** — https://www.shadcn-svelte.com/
- **shadcn/solid** — https://shadcn-solid.com/
- **shadcn/react-native** — https://rnr-docs.vercel.app/

Один и тот же дизайн-язык, тот же CLI-flow, для разных фреймворков.

**Что это значит для нас:** если когда-то FASTSAAS-mobile (React Native) — UI будет визуально консистентен с web без отдельного дизайн-усилия.

---

## 8.8 v0.dev — AI генерация UI напрямую в shadcn

https://v0.dev/

**v0** — Vercel-овский AI-инструмент, который **генерирует UI по text-описанию**, и выходной код — это **shadcn**.

Пример:

```
You: "Create a settings page for an org with 3 tabs: General, Members, Billing.
 Members tab has a table of users with role dropdown and remove button."

v0 generates: полностью рабочий React-компонент, использующий shadcn Button,
 Table, Tabs, DropdownMenu, AlertDialog. Готов копировать в репо.
```

Можно итерировать («сделай tabs горизонтальными», «добавь search field»,...) и v0 переписывает.

**Для FASTSAAS:** прототип нового экрана = 2 минуты в v0 → копи в репо → допили под наши данные. Особенно полезно для сложных форм и dashboard layouts.

---

## 8.9 MCP server для shadcn

С недавних пор shadcn имеет **официальный MCP server** — это значит **Claude Code и другие MCP-клиенты могут устанавливать компоненты напрямую через MCP**, без `npx`.

Документация (если ещё не релиз — то скоро): https://ui.shadcn.com/docs/mcp

Это значит:
- Я говорю Claude: «Добавь Login форму»
- Claude через MCP-tool вызывает shadcn-MCP, который устанавливает нужные компоненты, обновляет конфиг и пишет вызывающий код.
- Без выхода в терминал.

В перспективе это упрощает Vibe Coding до уровня «опиши что хочешь — Claude собирает».

---

## 8.10 Полная картина — что значит «использовать shadcn»

```
┌────────────────────────────────────────────────────────────────────┐
│ │
│ Когда мы решаем "shadcn" — мы получаем: │
│ │
│ ┌──────────────────────────────────────────────────────────────┐ │
│ │ CLI │ │
│ │ npx shadcn add <anything> │ │
│ └──────────────────────────────────────────────────────────────┘ │
│ │ │
│ ┌───────────────┼───────────────────┐ │
│ ▼ ▼ ▼ │
│ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ │
│ │ Components │ │ Blocks │ │ Charts │ │
│ │ (Button, │ │ (Login, │ │ (Bar, Line, │ │
│ │ Form,...) │ │ Sidebar) │ │ Area,...) │ │
│ └──────────────┘ └──────────────┘ └──────────────┘ │
│ │ │ │ │
│ └───────────────┼───────────────────┘ │
│ ▼ │
│ src/components/ui/ (твой код, твой репо) │
│ │
│ ┌──────────────────────────────────────────────────────────────┐ │
│ │ Theme system (CSS variables, tweakcn editor) │ │
│ └──────────────────────────────────────────────────────────────┘ │
│ │
│ ┌──────────────────────────────────────────────────────────────┐ │
│ │ Custom registry (FASTSAAS-specific компоненты — │ │
│ │ PropertyCard, ScenarioComparison, LeaseEditor) │ │
│ └──────────────────────────────────────────────────────────────┘ │
│ │
│ ┌──────────────────────────────────────────────────────────────┐ │
│ │ AI integration (v0.dev генерация, MCP для Claude) │ │
│ └──────────────────────────────────────────────────────────────┘ │
│ │
│ ┌──────────────────────────────────────────────────────────────┐ │
│ │ Ecosystem (Aceternity, Magic UI, Origin UI, 21st.dev) │ │
│ │ — десятки third-party registries, все совместимы с CLI │ │
│ └──────────────────────────────────────────────────────────────┘ │
│ │
└────────────────────────────────────────────────────────────────────┘
```

---

## 8.11 Практические следствия для FASTSAAS

### Что мы получаем «бесплатно»

1. **Готовый Login flow** — `npx shadcn add login-04` за 30 секунд.
2. **Готовый Dashboard layout** с sidebar и нав-меню — `npx shadcn add sidebar-07`.
3. **Готовые charts** для отображения результатов модели — `npx shadcn add chart-bar-mixed`.
4. **Theme switcher** — выбираем base palette на ui.shadcn.com/themes, экспортируем CSS, ставим в проект.
5. **AI-friendly код** — Claude видит каждый компонент, может его модифицировать и расширять.

### Что появится позже (FASTSAAS-specific custom registry)

Как только мы сделаем первые **FASTSAAS-specific компоненты** (для отображения Property, Lease, Scenario), мы можем создать:

```
platform/
└── frontend/
 └── registry/ # наш собственный registry
 ├── property-card.json
 ├── scenario-comparison.json
 ├── lease-editor.json
 └──...
```

И опубликовать как `https://design.fastsaas.com/registry/...`. Тогда **любой FASTSAAS-pilot или FASTSAAS-project** сможет:

```bash
npx shadcn add https://design.fastsaas.com/registry/property-card.json
```

→ получить готовый FASTSAAS-стиль PropertyCard в свой проект.

**Это distribution mechanism для нашего design system** — без npm-package, без upgrade pain, с полным контролем.

### Что это значит стратегически

shadcn-модель **идеально совпадает с нашей multi-repo архитектурой**:

```
platform = canonical UI implementation
 ↓ публикует
fastsaas-design-registry = FASTSAAS-style components
 ↓ потребляют
fastsaas-pilots/* = клиентские pilot deployments с custom branding
```

Каждый pilot копирует FASTSAAS-компоненты, но может их **визуально кастомизировать под клиента** (брендинг Acme Consulting vs Globex) — потому что код компонента в их репозитории.

Это **намного лучше** чем npm-package model, где кастомизация = props drilling или forking.

---

## 8.12 Что shadcn НЕ даёт

Чтобы быть честным:

- **Server-side data layer** — нет; используем TanStack Query.
- **Routing** — нет; используем TanStack Router.
- **Forms validation** — есть Form-обёртка, но валидация — через React Hook Form + Zod.
- **Animations** — есть basic transitions, для сложных — `framer-motion` отдельно.
- **State management** — нет; используем Zustand.
- **Mobile native** — есть отдельный shadcn/react-native, но это другой проект.

shadcn — **только UI слой**. Остальная архитектура — наша.

---

## TL;DR части 8

shadcn = **5 вещей в одном:**

1. **Философия** — Open Code, твой UI в твоём репо.
2. **CLI** — универсальный установщик любых registry.
3. **Каноничный registry** — components, blocks, charts, themes.
4. **Экосистема** — десятки совместимых third-party libraries.
5. **AI-integration** — v0.dev, MCP server, изначально Claude-friendly.

Для FASTSAAS это значит:
- ✅ Быстрый старт (готовые login-формы, dashboards, charts).
- ✅ Контроль (наш код, не npm dep).
- ✅ AI-friendly (Vibe Coding из коробки).
- ✅ Distribution (когда сделаем FASTSAAS-specific компоненты, публикуем через тот же CLI).
- ✅ Multi-tenant brand customisation (каждый pilot редактирует свои компоненты).

**Это не «выбор библиотеки» — это выбор экосистемы и подхода.**

---

## Дополнительные ссылки для shadcn-deep-dive

| Что | Ссылка |
|-----|--------|
| Philosophy / Open Code | https://ui.shadcn.com/docs |
| CLI documentation | https://ui.shadcn.com/docs/cli |
| Registry schema (как делать свой) | https://ui.shadcn.com/docs/registry |
| Blocks каталог | https://ui.shadcn.com/blocks |
| Charts каталог | https://ui.shadcn.com/charts |
| Theme editor | https://ui.shadcn.com/themes |
| Tweakcn — продвинутый theme editor | https://tweakcn.com/ |
| v0.dev — AI генерация | https://v0.dev/ |
| Aceternity UI (анимации) | https://ui.aceternity.com/ |
| Magic UI (визуальные эффекты) | https://magicui.design/ |
| Origin UI (расширенные варианты) | https://originui.com/ |
| 21st.dev (marketplace) | https://21st.dev/ |
| shadcn/vue port | https://www.shadcn-vue.com/ |
| shadcn/react-native | https://rnr-docs.vercel.app/ |
| Brian Lovin (shadcn автор) | https://brianlovin.com/ |
