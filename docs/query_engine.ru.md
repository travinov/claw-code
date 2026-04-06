# Модуль `src/query_engine.py`

## 1. Назначение

Модуль `src/query_engine.py` реализует прикладной слой портируемого движка запросов для Python-рабочего контура проекта `claw-code`.

Назначение модуля:

- хранить состояние активной сессии;
- принимать пользовательские сообщения;
- учитывать ограничения по количеству ходов и бюджету токенов;
- формировать текстовый или структурированный ответ;
- сохранять и восстанавливать сессию;
- строить итоговую сводку по рабочему пространству.

Модуль не выполняет сложную маршрутизацию самостоятельно. Он опирается на вспомогательные компоненты:

- `build_port_manifest()` для построения снимка рабочего пространства;
- `build_command_backlog()` и `build_tool_backlog()` для получения инвентарей команд и инструментов;
- `TranscriptStore` для хранения транскрипта;
- `save_session()` и `load_session()` для файловой персистентности.

## 2. Основные сущности

### `QueryEngineConfig`

Конфигурационная dataclass, которая задает ограничения и режим выдачи.

Поля:

| Поле | Тип | Назначение |
| --- | --- | --- |
| `max_turns` | `int` | Максимальное число пользовательских ходов в рамках одной сессии |
| `max_budget_tokens` | `int` | Общий лимит токенов ввода и вывода |
| `compact_after_turns` | `int` | Глубина хранения последних сообщений после компактации |
| `structured_output` | `bool` | Признак выдачи ответа в JSON-формате |
| `structured_retry_limit` | `int` | Количество повторных попыток сериализации JSON |

Пример:

```python
from src.query_engine import QueryEngineConfig

config = QueryEngineConfig(
    max_turns=4,
    max_budget_tokens=600,
    structured_output=True,
)
```

### `TurnResult`

Структура результата одного хода.

Поля:

| Поле | Тип | Назначение |
| --- | --- | --- |
| `prompt` | `str` | Исходный запрос пользователя |
| `output` | `str` | Сформированный ответ движка |
| `matched_commands` | `tuple[str, ...]` | Команды, сопоставленные запросу |
| `matched_tools` | `tuple[str, ...]` | Инструменты, сопоставленные запросу |
| `permission_denials` | `tuple[PermissionDenial, ...]` | Отказы доступа, относящиеся к ходу |
| `usage` | `UsageSummary` | Накопленная статистика использования |
| `stop_reason` | `str` | Причина завершения обработки |

### `QueryEnginePort`

Основной объект модуля. Инкапсулирует состояние сессии и операции жизненного цикла.

Ключевые атрибуты:

| Атрибут | Тип | Назначение |
| --- | --- | --- |
| `manifest` | `PortManifest` | Снимок структуры рабочего пространства |
| `config` | `QueryEngineConfig` | Ограничения и режимы работы |
| `session_id` | `str` | Идентификатор сессии |
| `mutable_messages` | `list[str]` | История пользовательских сообщений |
| `permission_denials` | `list[PermissionDenial]` | Совокупный журнал отказов по правам |
| `total_usage` | `UsageSummary` | Суммарный расход токенов |
| `transcript_store` | `TranscriptStore` | Хранилище транскрипта |

## 3. Публичные методы

### `QueryEnginePort.from_workspace() -> QueryEnginePort`

Создает новый объект движка на основе актуального рабочего пространства.

Параметры: отсутствуют.

Возвращаемое значение:

- новый экземпляр `QueryEnginePort` с автоматически сформированным `manifest`;
- новая сессия с уникальным `session_id`.

Когда использовать:

- при старте новой сессии;
- для генерации summary текущего состояния проекта;
- для сценариев CLI вроде `summary` и `flush-transcript`.

Пример:

```python
from src.query_engine import QueryEnginePort

engine = QueryEnginePort.from_workspace()
print(engine.session_id)
```

### `QueryEnginePort.from_saved_session(session_id: str) -> QueryEnginePort`

Восстанавливает объект движка из ранее сохраненной сессии.

Параметры:

| Параметр | Тип | Назначение |
| --- | --- | --- |
| `session_id` | `str` | Идентификатор файла сессии без расширения `.json` |

Возвращаемое значение:

- экземпляр `QueryEnginePort`, собранный из данных файлового хранилища.

Особенности:

- транскрипт создается в состоянии `flushed=True`;
- история сообщений переносится в `mutable_messages`.

Пример:

```python
engine = QueryEnginePort.from_saved_session("abc123")
print(engine.replay_user_messages())
```

### `submit_message(prompt, matched_commands=(), matched_tools=(), denied_tools=()) -> TurnResult`

Обрабатывает одно сообщение пользователя и обновляет состояние сессии.

Параметры:

| Параметр | Тип | Назначение |
| --- | --- | --- |
| `prompt` | `str` | Текст пользовательского сообщения |
| `matched_commands` | `tuple[str, ...]` | Предварительно сопоставленные команды |
| `matched_tools` | `tuple[str, ...]` | Предварительно сопоставленные инструменты |
| `denied_tools` | `tuple[PermissionDenial, ...]` | Отказы по правам, выявленные до обработки |

Возвращаемое значение:

- экземпляр `TurnResult`.

Логика работы:

1. Проверяет, не исчерпан ли лимит ходов.
2. Формирует служебную сводку по запросу, командам, tools и отказам.
3. Обновляет статистику использования.
4. При необходимости меняет `stop_reason` на `max_budget_reached`.
5. Сохраняет сообщение в историю и транскрипт.
6. Выполняет компактацию истории.

Пример:

```python
result = engine.submit_message(
    "review MCP tool",
    matched_commands=("review",),
    matched_tools=("MCPTool",),
)
print(result.output)
print(result.stop_reason)
```

### `stream_submit_message(prompt, matched_commands=(), matched_tools=(), denied_tools=())`

Потоковый вариант обработки сообщения. Возвращает генератор событий.

Параметры: совпадают с `submit_message`.

Формат событий:

| Тип события | Назначение |
| --- | --- |
| `message_start` | Старт обработки сообщения |
| `command_match` | Сообщение о найденных командах |
| `tool_match` | Сообщение о найденных инструментах |
| `permission_denial` | Сообщение об отказах по правам |
| `message_delta` | Итоговый текст ответа |
| `message_stop` | Финальная статистика и причина остановки |

Пример:

```python
for event in engine.stream_submit_message("review MCP tool"):
    print(event["type"])
```

### `compact_messages_if_needed() -> None`

Сокращает глубину хранения истории до значения `compact_after_turns`.

Применяется:

- после успешной обработки сообщения;
- для удержания объема состояния в предсказуемых пределах.

### `replay_user_messages() -> tuple[str, ...]`

Возвращает сообщения пользователя из транскрипта в неизмененном порядке.

Пример:

```python
messages = engine.replay_user_messages()
```

### `flush_transcript() -> None`

Помечает транскрипт как сброшенный. Используется перед сохранением сессии.

### `persist_session() -> str`

Сохраняет активную сессию в файловое хранилище и возвращает путь к созданному JSON-файлу.

Параметры: отсутствуют.

Возвращаемое значение:

- строковый путь к файлу сессии.

Пример:

```python
path = engine.persist_session()
print(path)
```

### `render_summary() -> str`

Формирует Markdown-сводку по Python-рабочему пространству.

Содержимое результата:

- manifest рабочего пространства;
- command surface;
- tool surface;
- состояние текущей сессии.

Пример:

```python
summary = QueryEnginePort.from_workspace().render_summary()
print(summary)
```

## 4. Внутренние методы

### `_format_output(summary_lines: list[str]) -> str`

Выбирает текстовый или JSON-формат ответа в зависимости от `structured_output`.

### `_render_structured_output(payload: dict[str, object]) -> str`

Пытается сериализовать полезную нагрузку в JSON и выполняет ограниченное число повторов при ошибке сериализации.

## 5. Примеры использования через CLI

Ниже приведены реальные сценарии, зафиксированные в `src/main.py` и `tests/test_porting_workspace.py`.

### Получение summary рабочего пространства

```bash
python -m src.main summary
```

Ожидаемый результат:

- вывод Markdown-заголовка `Python Porting Workspace Summary`;
- сведения о manifest, command surface и tool surface.

### Запуск ограниченного turn loop

```bash
python -m src.main turn-loop "review MCP tool" --max-turns 2 --structured-output
```

Ожидаемый результат:

- вывод секций `## Turn 1`, `## Turn 2`;
- для каждого хода отображается `stop_reason=...`.

### Сброс и сохранение транскрипта

```bash
python -m src.main flush-transcript "review MCP tool"
```

Ожидаемый результат:

- путь к файлу сохраненной сессии;
- признак `flushed=True`.

### Загрузка сохраненной сессии

```bash
python -m src.main load-session <session_id>
```

Ожидаемый результат:

- идентификатор сессии;
- количество сообщений;
- итоговые счетчики `in=` и `out=`.

## 6. Практические замечания

1. Модуль ориентирован на простую и детерминированную модель работы, пригодную для тестов и портирования.
2. Подсчет токенов выполнен эвристически через количество слов, а не через модельный tokenizer.
3. Потоковый режим не дублирует бизнес-логику, а использует `submit_message()` как единый источник результата.
4. Компактация истории влияет и на список сообщений, и на отдельное хранилище транскрипта.

## 7. Связанные файлы

- `src/main.py` — CLI-обертка над возможностями движка;
- `src/session_store.py` — сохранение и загрузка сессий;
- `src/transcript.py` — работа с транскриптом;
- `tests/test_porting_workspace.py` — сценарии проверки summary, turn loop и восстановления сессии.
