# Dark Factory — Prompt Studio

Веб-приложение для интерактивного уточнения задач с помощью LLM и автоматического создания тикетов в Ticket Manager.

---

## Стек

| Слой | Технология |
|---|---|
| Frontend | React 18, TypeScript, Vite, React Router v6, i18next |
| Backend | Python 3.12, FastAPI, SQLAlchemy 2 (async), Alembic |
| База данных | PostgreSQL 16 |
| LLM | OpenAI API (модель настраивается через `OPENAI_MODEL`) |
| Интеграция | Ticket Manager REST API |
| Прокси | nginx |
| Сборка | Docker + Docker Compose |

---

## Быстрый старт

### 1. Клонировать и настроить окружение

```bash
cp .env.example .env
# Отредактировать .env — обязательные поля отмечены ниже
```

### 2. Обязательные переменные в `.env`

| Переменная | Описание |
|---|---|
| `JWT_SECRET_KEY` | Случайная строка ≥ 32 символа. `python -c "import secrets; print(secrets.token_hex(32))"` |
| `INITIAL_ADMIN_PASSWORD` | Пароль первого администратора |
| `OPENAI_API_KEY` | Ключ OpenAI API |
| `TICKET_MANAGER_SERVICE_EMAIL` | Email сервисного аккаунта в Ticket Manager |
| `TICKET_MANAGER_SERVICE_PASSWORD` | Пароль сервисного аккаунта |

### 3. Запустить

```bash
docker compose up --build -d
```

Приложение будет доступно на `http://localhost` (или порт из `HTTP_PORT`).

При первом запуске автоматически:
- применяются миграции БД (`alembic upgrade head`)
- создаётся администратор с параметрами из `.env`

### 4. Войти

URL: `http://localhost/login`  
Email: значение `INITIAL_ADMIN_EMAIL` (по умолчанию `admin@dark-factory.local`)  
Пароль: значение `INITIAL_ADMIN_PASSWORD`

---

## Архитектура

```
nginx (80)
├── /api/*  →  backend:8000 (FastAPI)
│                ├── /api/v1/auth        JWT login / refresh
│                ├── /api/v1/sessions    Prompt refinement loop
│                ├── /api/v1/ticket-manager  Прокси к TM API
│                └── /api/v1/users       Admin CRUD
└── /*      →  frontend:80 (React SPA)
```

### Модель данных

```
users
  └── prompt_sessions (1:N)
        └── prompt_iterations (1:N)
```

Каждая `prompt_session` связана с проектом в Ticket Manager.  
Каждая `prompt_iteration` — это одна версия промпта (роль `user` или `assistant`).

### Цикл уточнения промпта

```
[Пользователь вводит промпт]
        ↓
[Создаётся сессия + iteration #1 (user)]
        ↓
[LLM улучшает → iteration #2 (assistant)]
        ↓
[Пользователь: одобрить / улучшить ещё / откатиться]
        ↓ (если "улучшить")
[Iteration #N (user comment) → iteration #N+1 (assistant)] ←┐
        ↓                                                      │
  (повторяется)  ───────────────────────────────────────────┘
        ↓ (если "одобрить")
[ApproveModal: пользователь редактирует title тикета]
        ↓
[POST /api/v1/sessions/{id}/approve]
   → создаётся проект (если new_project)
   → создаётся тикет с тегом needs-estimation
   → сессия переходит в статус approved]
```

---

## Переменные окружения (полный список)

### Backend

| Переменная | По умолчанию | Описание |
|---|---|---|
| `DATABASE_URL` | (из compose) | `postgresql+asyncpg://...` |
| `JWT_SECRET_KEY` | — | **Обязательно** |
| `JWT_ALGORITHM` | `HS256` | |
| `ACCESS_TOKEN_EXPIRES_MINUTES` | `30` | |
| `REFRESH_TOKEN_EXPIRES_DAYS` | `7` | |
| `INITIAL_ADMIN_EMAIL` | `admin@dark-factory.local` | |
| `INITIAL_ADMIN_PASSWORD` | — | **Обязательно** |
| `OPENAI_API_KEY` | — | **Обязательно** |
| `OPENAI_MODEL` | `gpt-4o-mini` | Любая chat-модель OpenAI |
| `OPENAI_BASE_URL` | (OpenAI default) | Для альтернативных провайдеров |
| `TICKET_MANAGER_BASE_URL` | `https://ticket-manager...` | |
| `TICKET_MANAGER_SERVICE_EMAIL` | — | **Обязательно** |
| `TICKET_MANAGER_SERVICE_PASSWORD` | — | **Обязательно** |
| `CORS_ALLOW_ORIGINS` | `http://localhost:5173` | Через запятую |

---

## Разработка (без Docker)

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example .env  # заполнить DATABASE_URL с localhost

alembic upgrade head
python scripts/seed.py
uvicorn src.main:app --reload
```

Swagger UI: `http://localhost:8000/api/docs`

### Frontend

```bash
cd frontend
npm install
npm run dev       # http://localhost:5173
```

Vite автоматически проксирует `/api` на `http://backend:8000` (или `localhost:8000` в dev).  
Для локальной разработки поменяй `target` в `vite.config.ts`.

---

## Тесты

### Backend

```bash
cd backend
pytest --cov=src --cov-report=term-missing
```

Порог покрытия: **80%** (настроен в `.coveragerc`).

### Frontend

```bash
cd frontend
npm test
```

Порог покрытия: **80% lines/functions** (настроен в `vite.config.ts`).

---

## Аутентификация

- JWT Access token (30 мин) + Refresh token (7 дней)
- Роли: `user` и `admin`
- Администраторы имеют доступ к `/admin` (управление пользователями)
- Самостоятельная регистрация отключена — пользователей создаёт только admin

### Сервисный аккаунт Ticket Manager

Создайте отдельного пользователя в вашем Ticket Manager (через его admin panel) и укажите его email/пароль в `.env`. Все операции с TM выполняются от его имени; авторство фиксируется в нашей БД.

---

## Структура проекта

```
dark-factory/
├── backend/
│   ├── src/
│   │   ├── core/         config, security, exceptions
│   │   ├── db/           session (engine, Base, get_db)
│   │   ├── models/       ORM models
│   │   ├── schemas/      Pydantic DTOs
│   │   ├── repositories/ DB access layer
│   │   ├── services/     business logic, LLM, TM client
│   │   └── api/v1/       FastAPI routers
│   ├── alembic/          migrations
│   ├── tests/            unit + integration
│   └── scripts/          seed.py
├── frontend/
│   ├── src/
│   │   ├── api/          Axios client + types
│   │   ├── context/      AuthContext
│   │   ├── components/   UI components by domain
│   │   ├── pages/        Router
│   │   ├── i18n/         en/ru translations
│   │   └── styles/       global.css
│   └── tests/            Vitest + RTL
├── nginx/
│   └── nginx.conf        reverse proxy
└── docker-compose.yml
```
