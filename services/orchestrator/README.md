# Dark Factory — Orchestrator Service

Автономный оркестратор рабочего процесса Dark Factory.  
Управляет FSM-состоянием тикетов, вызывает LLM для принятия решений,  
ведёт audit trail и сжимает историю через ContextDistiller.

---

## Архитектура

```
Human (Prompt Studio UI / прямой API)
  └── POST /api/v1/jobs/trigger  ──► Job создаётся в PostgreSQL
                                        │
                                        ▼  pg_notify
                              JobWorker (asyncio)
                                        │
                              ┌─────────┴──────────┐
                              │  asyncio.Semaphore  │  (max N параллельных)
                              └─────────┬──────────┘
                                        │
                              OrchestratorService
                                  │         │         │
                            FSM engine  LLM call  TM client
                                  │         │         │
                             (pure logic) OpenAI  TM API
                                        │
                              DocumentStore (MongoDB)
                              project_memory + ADRs
                                        │
                              AuditRepository (PostgreSQL)
```

### Компоненты

| Компонент | Назначение |
|---|---|
| **JobWorker** | asyncio-воркер, слушает PG NOTIFY, запускает jobs под семафором |
| **OrchestratorService** | Координирует один `orchestrate` job: FSM → LLM → TM → Audit |
| **DistillerService** | Координирует один `distill` job: LLM → MongoDB |
| **FSM engine** | Чистая логика переходов, без I/O |
| **LLM orchestrator** | Строит промпт, парсит JSON-решение |
| **ContextDistiller LLM** | Сжимает историю тикета в project_memory YAML |
| **DocumentStore** | Motor (async MongoDB): project_memory + ADRs |
| **TicketManagerClient** | HTTP-клиент к TM API с JWT авторизацией |

---

## Быстрый старт

### 1. Настроить окружение

```bash
cp env.example .env
# Заполнить обязательные поля
```

⚠️ `JWT_SECRET_KEY` **должен совпадать** с тем же ключом в Prompt Studio —  
оркестратор валидирует те же JWT-токены.

### 2. Запустить

```bash
docker compose up --build -d
```

Сервис будет доступен на `http://localhost:8080` (или `HTTP_PORT` из `.env`).  
Swagger UI: `http://localhost:8080/api/docs`

---

## API

### Основные endpoints

```
GET  /api/health                          — healthcheck

GET  /api/v1/jobs/pending-tickets         — список тикетов, ожидающих обработки
     ?project_id=<id>                     — фильтр по проекту

POST /api/v1/jobs/trigger                 — запустить обработку тикета
     { "ticket_id": "...", "project_id": "...", "priority": 0 }

GET  /api/v1/jobs                         — история jobs
     ?status=pending|running|done|failed
     ?ticket_id=<id>

GET  /api/v1/jobs/{job_id}                — детали одного job

GET  /api/v1/audit/{ticket_id}            — audit trail по тикету

GET  /api/v1/memory/{project_id}          — project memory
GET  /api/v1/memory/{project_id}/adrs     — ADR list
```

Все endpoints требуют `Authorization: Bearer <token>` — тот же JWT что выдаёт Prompt Studio.

---

## Флоу обработки тикета

```
Human нажимает "Отправить в работу" для тикета T в Prompt Studio
  │
  ├── POST /api/v1/jobs/trigger → Job создан (status=pending)
  │   └── pg_notify('df_new_job') → JobWorker просыпается
  │
  ├── JobWorker захватывает семафор → OrchestratorService.process_job()
  │   │
  │   ├── TM.get_ticket_full() — свежее состояние тикета
  │   ├── FSM.evaluate()       — чистая логика (без I/O)
  │   ├── TM.get_fsm_status_batch() — статусы зависимостей
  │   ├── DocumentStore.get_memory() + .list_adrs()
  │   ├── call_orchestrator_llm()   — LLM принимает решение
  │   ├── TM.update_fsm()           — применяем решение
  │   ├── AuditRepository.append()  — пишем в audit log
  │   └── (если done) → enqueue distill job
  │
  └── Job status = done | failed
```

---

## Переменные окружения

| Переменная | По умолчанию | Описание |
|---|---|---|
| `DATABASE_URL` | (из compose) | PostgreSQL async URL |
| `MONGO_URL` | `mongodb://mongo:27017` | MongoDB URL |
| `MONGO_DB_NAME` | `dark_factory_docs` | |
| `JWT_SECRET_KEY` | — | **Обязательно.** Должен совпадать с Prompt Studio |
| `OPENAI_API_KEY` | — | **Обязательно** |
| `OPENAI_MODEL` | `gpt-4o-mini` | |
| `TICKET_MANAGER_BASE_URL` | `https://...` | |
| `TICKET_MANAGER_SERVICE_EMAIL` | — | **Обязательно** |
| `TICKET_MANAGER_SERVICE_PASSWORD` | — | **Обязательно** |
| `WORKER_MAX_CONCURRENT_TICKETS` | `5` | Параллельность worker'а |
| `WORKER_POLL_INTERVAL_SECONDS` | `5` | Fallback poll если NOTIFY не пришёл |
| `DISTILLER_MAX_MEMORY_TOKENS` | `2000` | Лимит токенов для project_memory |

---

## Тесты

```bash
cd dark-factory-orchestrator
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest --cov=src --cov-report=term-missing
```

Порог покрытия: **80%** (настроен в `.coveragerc`).

---

## Структура проекта

```
src/
├── core/          config, exceptions, security (JWT verify)
├── db/            postgres.py (SQLAlchemy), mongo.py (Motor)
├── models/        ORM: Job, AuditLog
├── schemas/       Pydantic DTOs
├── repositories/  job_repo, audit_repo
├── services/
│   ├── tm_client/        Ticket Manager HTTP client
│   ├── llm/              orchestrator_llm.py (prompt build + parse)
│   ├── fsm/              engine.py (pure FSM logic)
│   ├── document_store/   store.py (MongoDB: memory + ADRs)
│   ├── distiller/        distiller.py (ContextDistiller LLM)
│   └── orchestrator_service.py  (main business logic)
├── api/v1/        jobs, audit, memory routers
├── workers/       job_worker.py (asyncio + PG LISTEN/NOTIFY)
└── main.py        FastAPI app factory + lifespan

alembic/           migrations (jobs table + audit_log + NOTIFY trigger)
tests/
├── unit/          FSM engine, Document Store, LLM parsing
└── integration/   Job repo, Audit repo, Jobs API, Orchestrator service
```

---

## Важные заметки

**`JWT_SECRET_KEY` должен совпадать с Prompt Studio.**  
Оркестратор не выдаёт токены — он только проверяет токены, выпущенные Prompt Studio backend.

**PostgreSQL NOTIFY trigger.**  
Миграция `0001_initial` создаёт триггер `trg_notify_new_job`, который автоматически  
посылает `NOTIFY df_new_job` при каждом INSERT в таблицу `jobs` со статусом `pending`.  
Это означает, что воркер просыпается мгновенно без поллинга.

**Зависимость от ticket-manager-extensions.md.**  
Оркестратор использует расширенные endpoints TM (FSM PATCH, `/orchestrator/pending`, batch status).  
Без них сервис запустится, но обработка тикетов не будет работать.
