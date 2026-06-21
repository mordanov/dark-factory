# Dark Factory — Required Ticket Manager Extensions

Этот документ описывает функциональность, которую необходимо добавить в существующий  
Ticket Manager, чтобы Workflow Orchestrator мог работать корректно.  
Документ предназначен для реализации через Claude Code.

---

## Контекст

Ticket Manager не имеет встроенного webhook-механизма.  
Оркестратор работает в режиме **polling**: он периодически опрашивает TM на наличие  
тикетов, требующих обработки. Поэтому TM должен предоставить специализированные  
endpoints для эффективного поллинга и хранить расширенные FSM-поля.

---

## 1. Расширение модели тикета — FSM-поля

### 1.1 Новые поля в таблице / документе тикета

| Поле | Тип | Описание |
|---|---|---|
| `fsm_status` | `enum` | Текущее состояние в FSM оркестратора. Отдельно от `status` TM. |
| `blocked_reason` | `string \| null` | Причина блокировки, выставляется оркестратором |
| `brainstorm_round` | `integer` | Счётчик раундов брейнсторма (0 по умолчанию) |
| `assigned_agent` | `string \| null` | ID агента, которому назначен тикет |
| `override_reason` | `string \| null` | Причина ручного override (заполняется человеком) |
| `last_orchestrator_run` | `datetime \| null` | Время последней обработки оркестратором |
| `orchestrator_errors` | `string[] \| null` | Последние ошибки оркестратора по этому тикету |

### 1.2 Допустимые значения `fsm_status`

```
backlog | triage | specification | architecture_review |
implementation | code_review | security_review |
testing | release | done | BLOCKED
```

### 1.3 API для обновления FSM-полей

```
PATCH /api/projects/{project_id}/tickets/{ticket_id}/fsm

Body:
{
  "fsm_status": "...",
  "blocked_reason": "...",      // null чтобы очистить
  "brainstorm_round": 0,
  "assigned_agent": "...",
  "override_reason": "...",
  "last_orchestrator_run": "ISO8601",
  "orchestrator_errors": []
}

Response: 200 { updated ticket }
```

**Примечание:** этот endpoint обновляет только FSM-поля, не затрагивая  
основные поля тикета (title, description, status TM).  
Авторизация: только сервисный аккаунт Dark Factory.

---

## 2. Polling Endpoints

### 2.1 Получить тикеты, ожидающие обработки оркестратором

```
GET /api/orchestrator/pending

Query params:
  project_id   (optional) — фильтр по проекту
  limit        (default: 20, max: 100)
  after_cursor (optional) — pagination cursor

Response:
{
  "tickets": [
    {
      "id": "...",
      "project_id": "...",
      "title": "...",
      "description": "...",
      "ticket_type": "feature | bugfix | improvement | other",
      "tags": [...],
      "status": "...",             // native TM status
      "fsm_status": "...",
      "blocked_reason": null,
      "brainstorm_round": 0,
      "assigned_agent": null,
      "last_orchestrator_run": null,
      "dependencies": [...],       // list of ticket IDs
      "subtasks": [...],
      "created_at": "...",
      "updated_at": "..."
    }
  ],
  "next_cursor": "...",
  "total_pending": 42
}
```

**Логика "pending":** тикет считается ожидающим если:
- `fsm_status` не равен `done`
- И (`last_orchestrator_run` is null ИЛИ `updated_at` > `last_orchestrator_run`)

### 2.2 Получить конкретный тикет с FSM-полями

```
GET /api/projects/{project_id}/tickets/{ticket_id}/full

Response: полный объект тикета включая все FSM-поля (см. 1.1)
```

### 2.3 Список тикетов проекта с FSM-статусом (расширение существующего)

```
GET /api/projects/{project_id}/tickets?include_fsm=true

Добавляет FSM-поля к каждому тикету в ответе существующего endpoint.
```

---

## 3. Override Endpoint

Позволяет человеку вручную выставить `override: true` для конкретного тикета,  
чтобы оркестратор проигнорировал провальный gate на следующем polling-цикле.

```
POST /api/projects/{project_id}/tickets/{ticket_id}/override

Body:
{
  "override": true,
  "override_reason": "Urgent hotfix — skipping security_check with PM approval"
}

Response: 200 { updated ticket }
```

**Авторизация:** только пользователи с ролью `admin`.  
После обработки оркестратором поле `override` сбрасывается в `false`.

---

## 4. Agent Event Log (Audit Trail)

TM хранит лог событий оркестратора по каждому тикету.  
Это отдельная таблица / коллекция, не комментарии к тикету.

```
POST /api/tickets/{ticket_id}/audit

Body:
{
  "event": "ADVANCE | BLOCK | ASSIGN | WAIT | ...",
  "actor": "orchestrator",
  "from_state": "...",
  "to_state": "...",
  "details": "...",
  "timestamp": "ISO8601"
}

Response: 201 { audit_entry_id }
```

```
GET /api/tickets/{ticket_id}/audit

Response:
{
  "entries": [
    {
      "id": "...",
      "event": "...",
      "actor": "...",
      "from_state": "...",
      "to_state": "...",
      "details": "...",
      "timestamp": "..."
    }
  ]
}
```

---

## 5. Dependency Status Batch Lookup

Для проверки зависимостей оркестратору нужен batch-запрос статусов.

```
POST /api/tickets/fsm-status-batch

Body:
{
  "ticket_ids": ["id-1", "id-2", "id-3"]
}

Response:
{
  "statuses": {
    "id-1": { "fsm_status": "done", "title": "..." },
    "id-2": { "fsm_status": "implementation", "title": "..." },
    "id-3": { "fsm_status": "BLOCKED", "blocked_reason": "..." }
  }
}
```

---

## 6. Tag Management

Нужен endpoint для добавления/удаления тегов без полного PATCH тикета.  
Критично для управления тегом `needs-estimation`.

```
POST /api/projects/{project_id}/tickets/{ticket_id}/tags
Body: { "add": ["tag1"], "remove": ["needs-estimation"] }
Response: 200 { "tags": [...] }
```

---

## 7. Сводная таблица — что добавить

| Приоритет | Что | Endpoint / Поле |
|---|---|---|
| 🔴 Критично | FSM-поля на тикете | модель + `PATCH /fsm` |
| 🔴 Критично | Polling endpoint | `GET /orchestrator/pending` |
| 🔴 Критично | Полный тикет с FSM | `GET /.../tickets/{id}/full` |
| 🔴 Критично | Audit log (write) | `POST /tickets/{id}/audit` |
| 🟡 Важно | Override endpoint | `POST /.../override` |
| 🟡 Важно | Tag management | `POST /.../tags` |
| 🟡 Важно | Batch FSM status | `POST /tickets/fsm-status-batch` |
| 🟢 Желательно | Audit log (read) | `GET /tickets/{id}/audit` |
| 🟢 Желательно | `include_fsm` query param | расширение существующего list |

---

## 8. Примечания по авторизации

Все новые endpoints должны принимать тот же Bearer-токен что и существующий TM API.  
Сервисный аккаунт Dark Factory (`TICKET_MANAGER_SERVICE_EMAIL`) должен иметь право  
вызывать все endpoints из этого документа.  
`/override` дополнительно требует роли `admin` на стороне TM.
