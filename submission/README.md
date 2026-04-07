# Sber VibeCoding Challenge #2 Submission

## Публичные репозитории

1. Форк с документированным модулем:
[https://github.com/travinov/claw-code](https://github.com/travinov/claw-code)
2. Qwen extension:
[https://github.com/travinov/gigadoc-extension](https://github.com/travinov/gigadoc-extension)
3. MCP tool server:
[https://github.com/travinov/gigadoc-mcp](https://github.com/travinov/gigadoc-mcp)

## Что сделано в форке `claw-code`

1. Задокументирован `src/query_engine.py` в официальном русскоязычном стиле.
2. Добавлен модульный документ `docs/query_engine.ru.md`.
3. Добавлены файлы для сдачи:
   - `submission/dialogue.md`
   - `submission/style-report.md`

## Как установить и использовать комплект

1. Клонировать extension и MCP:

```bash
git clone https://github.com/travinov/gigadoc-extension.git
git clone https://github.com/travinov/gigadoc-mcp.git
```

2. Собрать MCP server:

```bash
cd gigadoc-mcp
npm install
npm run build
```

3. Подключить extension к Qwen:

```bash
cd ../gigadoc-extension
qwen extensions link .
export GIGADOC_MCP_ENTRY="/absolute/path/to/gigadoc-mcp/dist/src/index.js"
```

4. Использовать в Qwen CLI:

```text
/doc:sber /absolute/path/to/module.py
```

## Практическая польза решения

1. Быстрая генерация документации по Python-модулям по единому стандарту.
2. Снижение разброса качества между авторами документации.
3. Валидация структуры документа перед публикацией.
4. Применимость к типовым задачам: API docs, onboarding docs, release docs.
