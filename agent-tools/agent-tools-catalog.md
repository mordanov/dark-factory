# Dark Factory — Agent Tools Catalog

Этот документ описывает инструменты (tools), которые потребуются агентам  
по мере перехода от LLM-only к гибридному режиму (LLM + реальные действия).  
Текущий статус каждого инструмента: **planned** / **in-progress** / **available**.

Документ предназначен для поэтапной реализации через Claude Code.

---

## Принципы

- Каждый инструмент — это отдельная функция, вызываемая агентом через MCP или  
  function calling (OpenAI tools API / Anthropic tool_use).
- Инструменты не знают о FSM. Они выполняют атомарные действия и возвращают  
  структурированный результат. Оркестратор интерпретирует результаты.
- Все инструменты должны быть **идемпотентными** где возможно.
- Все инструменты должны возвращать `{ success, result, error }`.

---

## 1. Инструменты чтения кода (все агенты)

### `read_file`
```
Описание: Прочитать содержимое файла из репозитория.
Статус: available
Агенты: все
Параметры:
  path: string          — путь относительно корня репозитория
  ref: string           — git ref (branch/commit), default: main
Возвращает:
  content: string
  size_bytes: int
  language: string      — определяется по расширению
```

### `list_files`
```
Описание: Список файлов в директории.
Статус: available
Агенты: все
Параметры:
  path: string
  recursive: bool       — default: false
  pattern: string       — glob, например "*.py"
Возвращает:
  files: string[]
```

### `search_code`
```
Описание: Полнотекстовый поиск по репозиторию (grep-like).
Статус: available
Агенты: software_architect, backend, frontend, code_reviewer, security_architect
Параметры:
  query: string
  path_filter: string   — optional glob
  case_sensitive: bool  — default: false
Возвращает:
  matches: [{ file, line, content }]
```

### `get_diff`
```
Описание: Git diff между двумя ref'ами или последний diff PR/branch.
Статус: available
Агенты: code_reviewer, security_architect, autotester
Параметры:
  base_ref: string
  head_ref: string
  path_filter: string   — optional
Возвращает:
  diff: string          — unified diff format
  files_changed: string[]
  stats: { additions, deletions, files }
```

---

## 2. Инструменты записи кода (backend, frontend, designer)

### `write_file`
```
Описание: Создать или перезаписать файл в рабочей ветке агента.
Статус: planned
Агенты: backend, frontend, designer
Параметры:
  path: string
  content: string
  commit_message: string
  branch: string        — ветка агента, создаётся если не существует
Возвращает:
  commit_sha: string
```

### `create_pull_request`
```
Описание: Открыть PR из ветки агента в main/develop.
Статус: planned
Агенты: backend, frontend, designer
Параметры:
  title: string
  body: string          — описание изменений + ссылка на тикет
  head_branch: string
  base_branch: string   — default: main
  ticket_id: string     — для автолинковки
Возвращает:
  pr_id: string
  pr_url: string
```

### `request_review`
```
Описание: Назначить code_reviewer на PR.
Статус: planned
Агенты: backend, frontend
Параметры:
  pr_id: string
  reviewer_agent: string — default: "code_reviewer"
Возвращает:
  success: bool
```

---

## 3. Инструменты тестирования (autotester)

### `run_tests`
```
Описание: Запустить тест-сьют и вернуть результаты.
Статус: planned
Агенты: autotester
Реализация: вызов pytest / npm test в изолированном контейнере
Параметры:
  test_path: string     — папка или файл, default: весь проект
  coverage: bool        — собирать coverage, default: true
  timeout_seconds: int  — default: 300
Возвращает:
  passed: int
  failed: int
  errors: int
  coverage_percent: float
  uncovered_paths: string[]
  output: string        — stdout/stderr (обрезано до 10k символов)
  exit_code: int
```

### `get_test_report`
```
Описание: Получить последний сохранённый отчёт о тестировании для тикета.
Статус: planned
Агенты: autotester, orchestrator (для gate test_coverage)
Параметры:
  ticket_id: string
Возвращает:
  report: { passed, failed, coverage_percent, uncovered_paths, timestamp }
```

### `write_test`
```
Описание: Создать файл с unit/integration тестами.
Статус: planned
Агенты: autotester
Параметры:
  path: string
  content: string
  framework: string     — pytest | jest | vitest
  commit_message: string
  branch: string
Возвращает:
  commit_sha: string
```

---

## 4. Инструменты статического анализа (code_reviewer, security_architect)

### `run_linter`
```
Описание: Запустить линтер на файлах из diff.
Статус: planned
Агенты: code_reviewer
Реализация: ruff (Python), eslint (JS/TS)
Параметры:
  files: string[]
  config_path: string   — optional
Возвращает:
  issues: [{ file, line, rule, severity, message }]
  error_count: int
  warning_count: int
```

### `run_security_scan`
```
Описание: SAST-сканирование кода на уязвимости.
Статус: planned
Агенты: security_architect
Реализация: bandit (Python), semgrep (универсальный)
Параметры:
  files: string[]       — или весь репозиторий если пустой
  severity_threshold: string — high | medium | low, default: medium
Возвращает:
  findings: [{ severity, rule_id, file, line, description, cwe }]
  scan_duration_ms: int
```

### `check_dependencies`
```
Описание: Проверить зависимости на known CVE.
Статус: planned
Агенты: security_architect
Реализация: safety (Python), npm audit (Node)
Параметры:
  manifest_path: string — requirements.txt / package.json
Возвращает:
  vulnerabilities: [{ package, version, cve, severity, fix_version }]
  total_count: int
```

---

## 5. Инструменты DevOps (devops)

### `trigger_ci`
```
Описание: Запустить CI pipeline для PR или ветки.
Статус: planned
Агенты: devops
Реализация: GitHub Actions API / GitLab CI API
Параметры:
  ref: string           — branch или PR ref
  pipeline_name: string — default: "main"
Возвращает:
  run_id: string
  status: string        — queued | running | success | failed
  url: string
```

### `get_ci_status`
```
Описание: Проверить статус CI run.
Статус: planned
Агенты: devops, orchestrator
Параметры:
  run_id: string
Возвращает:
  status: string
  duration_seconds: int
  steps: [{ name, status, duration }]
  logs_url: string
```

### `deploy`
```
Описание: Задеплоить артефакт в целевое окружение.
Статус: planned
Агенты: devops
⚠️  Требует явного human approval перед вызовом (флаг в payload от оркестратора).
Параметры:
  environment: string   — staging | production
  artifact_ref: string  — commit sha или tag
  ticket_id: string
Возвращает:
  deployment_id: string
  status: string
  url: string           — URL задеплоенного окружения
```

---

## 6. Инструменты Document Store (все агенты через orchestrator)

Доступ к project memory и ADR List через единый интерфейс.  
Физическое хранилище: MongoDB (или аналог).

### `fetch_project_memory`
```
Описание: Получить сжатую project memory для проекта.
Статус: available
Агенты: orchestrator (инжектирует в контекст вызова агента)
Параметры:
  project_id: string
  ticket_id: string     — для фильтрации релевантного контекста
  max_tokens: int       — default: 2000
Возвращает:
  memory: string        — YAML-сводка
  source_ticket_ids: string[]
```

### `fetch_adrs`
```
Описание: Получить список ADR для проекта.
Статус: available
Агенты: orchestrator, software_architect
Параметры:
  project_id: string
  status_filter: string — accepted | proposed | all, default: accepted
  domain_filter: string — optional тег домена (auth, database, api...)
Возвращает:
  adrs: [{ id, title, status, summary, date }]
```

### `save_adr`
```
Описание: Сохранить новый ADR в Document Store.
Статус: planned
Агенты: orchestrator (только он генерирует ADR)
Параметры:
  project_id: string
  adr: string           — полный markdown текст ADR
  ticket_id: string
Возвращает:
  adr_id: string
  adr_number: int
```

---

## 7. Инструменты Ticket Manager (project_manager, project_administrator)

Обёртки над TM API (включая расширения из ticket-manager-extensions.md).

### `update_ticket_fsm`
```
Описание: Обновить FSM-поля тикета.
Статус: available (после реализации расширений TM)
Агенты: orchestrator (только он пишет FSM-состояние)
Параметры:
  ticket_id: string
  fsm_status: string
  blocked_reason: string | null
  assigned_agent: string | null
Возвращает:
  success: bool
```

### `manage_tags`
```
Описание: Добавить/удалить теги тикета.
Статус: available (после реализации расширений TM)
Агенты: project_manager, project_administrator
Параметры:
  ticket_id: string
  add: string[]
  remove: string[]
Возвращает:
  tags: string[]
```

### `create_subtask`
```
Описание: Создать subtask-тикет, привязанный к родительскому.
Статус: available (зависит от TM API)
Агенты: project_manager, software_architect
Параметры:
  parent_ticket_id: string
  title: string
  description: string
  ticket_type: string
  assigned_agent: string
Возвращает:
  ticket_id: string
```

---

## 8. Дорожная карта реализации

```
Фаза 1 (текущая) — LLM-only
  Агенты работают без инструментов.
  Весь ввод/вывод через текстовые промпты.
  Оркестратор управляет только FSM через TM API.

Фаза 2 — Read tools
  read_file, list_files, search_code, get_diff
  fetch_project_memory, fetch_adrs
  Агенты получают реальный контекст кода.

Фаза 3 — Write + Test tools
  write_file, create_pull_request
  run_tests, write_test, run_linter

Фаза 4 — Security + Deploy tools
  run_security_scan, check_dependencies
  trigger_ci, get_ci_status, deploy (с human approval gate)
```

---

## 9. Формат возврата (стандарт для всех инструментов)

```json
{
  "tool": "tool_name",
  "success": true,
  "result": { },
  "error": null,
  "duration_ms": 0,
  "timestamp": "ISO8601"
}
```

При ошибке:
```json
{
  "tool": "tool_name",
  "success": false,
  "result": null,
  "error": {
    "code": "FILE_NOT_FOUND | TIMEOUT | AUTH_FAILED | ...",
    "message": "...",
    "retryable": true
  },
  "duration_ms": 0,
  "timestamp": "ISO8601"
}
```
