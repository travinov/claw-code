# Sber VibeCoding Challenge #2 Submission

## Публичные репозитории

1. Форк с документированным модулем:
[https://github.com/travinov/claw-code](https://github.com/travinov/claw-code)
2. Qwen extension:
[https://github.com/travinov/qwen-sber-doc-extension](https://github.com/travinov/qwen-sber-doc-extension)
3. MCP tool server:
[https://github.com/travinov/qwen-sber-doc-mcp](https://github.com/travinov/qwen-sber-doc-mcp)

## Что сделано в форке `claw-code`

1. Задокументирован `src/query_engine.py` в официальном русскоязычном стиле.
2. Добавлен модульный документ `docs/query_engine.ru.md`.
3. Добавлены файлы для сдачи:
   - `submission/dialogue.md`
   - `submission/style-report.md`

## Как установить и использовать комплект

1. Клонировать extension и MCP:

```bash
git clone https://github.com/travinov/qwen-sber-doc-extension.git
git clone https://github.com/travinov/qwen-sber-doc-mcp.git
```

2. Собрать MCP server:

```bash
cd qwen-sber-doc-mcp
npm install
npm run build
```

3. Подключить extension к Qwen:

```bash
cd ../qwen-sber-doc-extension
qwen extensions link .
export QWEN_SBER_DOC_MCP_ENTRY="/absolute/path/to/qwen-sber-doc-mcp/dist/src/index.js"
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
