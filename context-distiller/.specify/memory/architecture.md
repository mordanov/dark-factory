# Dark Factory — ContextDistiller: High-Level Architecture

ContextDistiller — автономный компонент Dark Factory, который сжимает  
историю завершённых тикетов в структурированную «память проекта»,  
доступную оркестратору и агентам в каждом последующем цикле работы.

---

## Зачем нужен ContextDistiller

LLM имеет ограниченное контекстное окно. По мере роста проекта история тикетов,  
принятых решений и изменений кода перестаёт помещаться в один вызов.  
ContextDistiller решает это через **прогрессивное сжатие**:  
каждый закрытый тикет превращается в компактную запись, которая сохраняет  
только то, что важно для будущих решений.

---

## Место в архитектуре Dark Factory

```
Ticket Manager
  └── ticket.fsm_status → "done"
        └── Orchestrator устанавливает context_distiller_trigger: true
              └── Orchestrator Service публикует задачу в очередь
                    └── ContextDistiller Worker получает задачу
                          ├── собирает данные тикета + diff + audit log
                          ├── вызывает LLM для компрессии
                          └── сохраняет в Document Store (MongoDB)
                                └── Orchestrator читает при следующем вызове
```

ContextDistiller не вызывается синхронно — это **async worker**,  
запускаемый из очереди задач (Redis + Celery или аналог).

---

## Компоненты

### 1. Trigger (внутри Orchestrator Service)

Когда оркестратор выставляет `context_distiller_trigger: true`,  
Orchestrator Service публикует задачу в очередь:

```json
{
  "task": "distill",
  "ticket_id": "...",
  "project_id": "...",
  "timestamp": "ISO8601"
}
```

### 2. Data Collector

Собирает все входные данные перед вызовом LLM:

| Источник | Что собирается |
|---|---|
| Ticket Manager API | Полный тикет: title, description, ticket_type, tags, fsm_status history |
| TM Audit Log API | Все события оркестратора по тикету |
| Git / Code tool | Список изменённых файлов, diff (если доступен — Фаза 2+) |
| Document Store | Текущий snapshot project_memory (для инкрементального обновления) |
| Document Store | Список существующих ADR проекта |

### 3. Distillation LLM Call

Один вызов OpenAI/Claude с системным промптом ContextDistiller'а.

**Входной контекст:**
```
- Полный тикет
- Audit trail (список решений оркестратора)
- Текущая project_memory (для инкрементального merge)
- Список ADR (только ID + title, без полного текста)
- (Фаза 2+) Git diff summary
```

**Задача LLM:**
1. Выделить из тикета ключевые факты, решения, риски.
2. Определить, какие части текущей project_memory устарели или противоречат новому тикету.
3. Сгенерировать обновлённую project_memory (merge старой + новой информации).
4. Вернуть строго структурированный YAML.

**System prompt (краткое описание):**
```
Ты — ContextDistiller. Твоя задача: создать сжатую, точную и актуальную
"память проекта" на основе завершённого тикета и существующего контекста.
Ты не пишешь код. Ты не принимаешь решения. Ты только дистиллируешь факты.
Правила:
- Убирай устаревшую информацию (если новый тикет её отменяет).
- Сохраняй риски, даже если они не были решены.
- Упоминай изменённые файлы (по имени, без содержимого).
- Максимальный размер output: {max_tokens} токенов.
- Формат ответа: только YAML, никакой прозы.
```

**Формат output (project_memory YAML):**
```yaml
project_id: "..."
last_updated: "ISO8601"
last_ticket_id: "..."

architecture:
  - "JWT middleware добавлен в auth.py, применяется ко всем /api/* маршрутам"
  - "PostgreSQL используется для всего персистентного хранения (ADR-012)"

recent_changes:
  - ticket_id: "AUTH-003"
    summary: "Добавлен refresh token с хранением в HttpOnly cookie"
    files_changed: ["auth.py", "jwt.py", "tests/test_auth.py"]
    risks:
      - "Мобильный клиент пока не обрабатывает истечение access token"

open_risks:
  - "Rate limiting на /api/auth/login не реализован"
  - "Миграция users.password_hash не покрыта rollback-скриптом"

known_constraints:
  - "Все эндпоинты должны быть async (ADR-015)"
  - "Покрытие тестами ≥ 80% обязательно для перехода в testing"

tech_stack:
  backend: "Python 3.12, FastAPI, SQLAlchemy async"
  frontend: "React 18, TypeScript, Vite"
  database: "PostgreSQL 16"
  infra: "Docker Compose, nginx"
```

### 4. Document Store (MongoDB)

Хранит два вида документов:

**Collection: `project_memory`**
```json
{
  "_id": "project_id",
  "content": "... YAML string ...",
  "version": 42,
  "last_ticket_id": "...",
  "updated_at": "ISO8601"
}
```
Один документ на проект. Полностью перезаписывается при каждой дистилляции.

**Collection: `adrs`**
```json
{
  "_id": "ADR-012",
  "project_id": "...",
  "title": "...",
  "status": "accepted",
  "content": "... полный markdown ...",
  "ticket_id": "...",
  "created_at": "ISO8601",
  "updated_at": "ISO8601"
}
```
ADR создаются оркестратором (gate `adr_generation`), никогда не перезаписываются —  
только добавляются новые или меняется `status` (proposed → accepted → superseded).

### 5. Версионирование и откат

`project_memory` хранит только **последнюю версию**.  
Для аудита и возможного отката ведётся отдельная коллекция `project_memory_history`:

```json
{
  "project_id": "...",
  "version": 41,
  "content": "... предыдущая версия ...",
  "ticket_id": "...",
  "created_at": "ISO8601"
}
```

История хранится последние **N версий** (настраивается, рекомендуется 20).

---

## Интерфейс (API ContextDistiller Service)

ContextDistiller работает как отдельный сервис с минимальным API.

```
POST /distill
Body: { "ticket_id": "...", "project_id": "..." }
Response: 202 Accepted  ← задача принята в очередь, не синхронный вызов

GET /status/{task_id}
Response: { "status": "queued | running | done | failed", "error": null }

GET /memory/{project_id}
Response: { "content": "yaml string", "version": 42, "updated_at": "..." }

GET /adrs/{project_id}
Query: ?status=accepted&domain=auth
Response: { "adrs": [...] }

POST /adrs/{project_id}
Body: { "adr": "markdown string", "ticket_id": "...", "adr_number": 13 }
Response: 201 { "adr_id": "ADR-013" }
```

---

## Стек реализации

| Компонент | Технология |
|---|---|
| Worker framework | Python 3.12 + Celery |
| Queue | Redis |
| Document Store | MongoDB (через Motor — async driver) |
| LLM | OpenAI API (claude-sonnet-4-6 как альтернатива) |
| API | FastAPI (тот же паттерн что у Orchestrator Service) |
| Конфигурация | Pydantic Settings + `.env` (те же переменные что у backend) |

---

## Дорожная карта

```
Фаза 1 — Основа
  ✦ Document Store (MongoDB) с коллекциями project_memory и adrs
  ✦ Базовый Distillation LLM call (без git diff)
  ✦ Celery worker + Redis queue
  ✦ /distill, /memory, /adrs endpoints
  ✦ Оркестратор читает memory/adrs и инжектирует в контекст агентов

Фаза 2 — Обогащение
  ✦ Интеграция с git (изменённые файлы + diff summary)
  ✦ Фильтрация project_memory по домену (auth, api, database...)
  ✦ project_memory_history с возможностью отката

Фаза 3 — Оптимизация
  ✦ Семантический поиск по project_memory (embeddings)
  ✦ Автоматическое определение устаревших записей
  ✦ Incremental distillation (не полная перезапись при малых тикетах)
```

---

## Связи с другими компонентами

```
Orchestrator Service
  ├── пишет в очередь → ContextDistiller Worker
  └── читает из Document Store ← (через fetch_project_memory tool)

Prompt Studio Backend
  └── не взаимодействует напрямую (только через TM и Orchestrator)

Ticket Manager
  └── источник данных для Data Collector (тикет + audit log)

Agent Tools (Фаза 2+)
  └── read_file, get_diff → обогащают входные данные для дистилляции
```
