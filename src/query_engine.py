"""Инструменты портируемого движка запросов для Python-рабочего контура.

Модуль реализует упрощенный runtime-слой поверх инвентарей команд и tools.
Он отвечает за:

- хранение состояния диалога;
- учет ограничений по ходам и токенам;
- формирование текстового или структурированного ответа;
- восстановление и сохранение сессии;
- выпуск краткой сводки по рабочему пространству.

Основные сущности:

- `QueryEngineConfig` — параметры выполнения;
- `TurnResult` — результат одного хода;
- `QueryEnginePort` — объект состояния и поведения движка.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from uuid import uuid4

from .commands import build_command_backlog
from .models import PermissionDenial, UsageSummary
from .port_manifest import PortManifest, build_port_manifest
from .session_store import StoredSession, load_session, save_session
from .tools import build_tool_backlog
from .transcript import TranscriptStore


@dataclass(frozen=True)
class QueryEngineConfig:
    """Конфигурация выполнения движка запросов.

    Параметры:
    - `max_turns`: максимально допустимое количество пользовательских ходов.
    - `max_budget_tokens`: общий лимит токенов ввода и вывода.
    - `compact_after_turns`: глубина хранения последних сообщений после компактации.
    - `structured_output`: признак выдачи ответа в JSON-формате.
    - `structured_retry_limit`: число повторных попыток сериализации структурированного ответа.
    """

    max_turns: int = 8
    max_budget_tokens: int = 2000
    compact_after_turns: int = 12
    structured_output: bool = False
    structured_retry_limit: int = 2


@dataclass(frozen=True)
class TurnResult:
    """Результат обработки одного пользовательского сообщения.

    Параметры:
    - `prompt`: исходный запрос пользователя.
    - `output`: итоговый ответ движка.
    - `matched_commands`: команды, сопоставленные маршрутизатором.
    - `matched_tools`: инструменты, сопоставленные маршрутизатором.
    - `permission_denials`: зафиксированные отказы по правам.
    - `usage`: накопленная статистика использования.
    - `stop_reason`: причина завершения обработки хода.
    """

    prompt: str
    output: str
    matched_commands: tuple[str, ...]
    matched_tools: tuple[str, ...]
    permission_denials: tuple[PermissionDenial, ...]
    usage: UsageSummary
    stop_reason: str


@dataclass
class QueryEnginePort:
    """Состояние и операции движка запросов.

    Экземпляр объединяет конфигурацию, журнал сообщений, сведения об отказах
    доступа и накопленную статистику использования.

    Параметры:
    - `manifest`: снимок структуры рабочего пространства.
    - `config`: параметры выполнения движка.
    - `session_id`: идентификатор сессии.
    - `mutable_messages`: список пользовательских сообщений в активной сессии.
    - `permission_denials`: накопленные отказы в доступе к инструментам.
    - `total_usage`: суммарное потребление токенов.
    - `transcript_store`: хранилище транскрипта сессии.

    Пример:
    ```python
    engine = QueryEnginePort.from_workspace()
    result = engine.submit_message("review MCP tool")
    print(result.stop_reason)
    ```
    """

    manifest: PortManifest
    config: QueryEngineConfig = field(default_factory=QueryEngineConfig)
    session_id: str = field(default_factory=lambda: uuid4().hex)
    mutable_messages: list[str] = field(default_factory=list)
    permission_denials: list[PermissionDenial] = field(default_factory=list)
    total_usage: UsageSummary = field(default_factory=UsageSummary)
    transcript_store: TranscriptStore = field(default_factory=TranscriptStore)

    @classmethod
    def from_workspace(cls) -> 'QueryEnginePort':
        """Создает движок на основе актуального состояния рабочего пространства.

        Возвращает:
        - Экземпляр `QueryEnginePort` с новым идентификатором сессии и
          конфигурацией по умолчанию.
        """

        return cls(manifest=build_port_manifest())

    @classmethod
    def from_saved_session(cls, session_id: str) -> 'QueryEnginePort':
        """Восстанавливает движок из ранее сохраненной сессии.

        Параметры:
        - `session_id`: идентификатор сохраненной сессии без расширения файла.

        Возвращает:
        - Экземпляр `QueryEnginePort`, восстановленный из файлового хранилища.
        """

        stored = load_session(session_id)
        transcript = TranscriptStore(entries=list(stored.messages), flushed=True)
        return cls(
            manifest=build_port_manifest(),
            session_id=stored.session_id,
            mutable_messages=list(stored.messages),
            total_usage=UsageSummary(stored.input_tokens, stored.output_tokens),
            transcript_store=transcript,
        )

    def submit_message(
        self,
        prompt: str,
        matched_commands: tuple[str, ...] = (),
        matched_tools: tuple[str, ...] = (),
        denied_tools: tuple[PermissionDenial, ...] = (),
    ) -> TurnResult:
        """Обрабатывает одно сообщение и обновляет состояние сессии.

        Параметры:
        - `prompt`: текст сообщения пользователя.
        - `matched_commands`: команды, заранее сопоставленные с запросом.
        - `matched_tools`: инструменты, заранее сопоставленные с запросом.
        - `denied_tools`: список отказов по правам, относящихся к запросу.

        Возвращает:
        - `TurnResult` с итоговым ответом, статистикой и причиной остановки.

        Особенности:
        - При достижении `max_turns` состояние сессии не изменяется.
        - При превышении бюджета токенов в результате обработки причина
          остановки меняется на `max_budget_reached`.
        """

        if len(self.mutable_messages) >= self.config.max_turns:
            output = f'Max turns reached before processing prompt: {prompt}'
            return TurnResult(
                prompt=prompt,
                output=output,
                matched_commands=matched_commands,
                matched_tools=matched_tools,
                permission_denials=denied_tools,
                usage=self.total_usage,
                stop_reason='max_turns_reached',
            )

        summary_lines = [
            f'Prompt: {prompt}',
            f'Matched commands: {", ".join(matched_commands) if matched_commands else "none"}',
            f'Matched tools: {", ".join(matched_tools) if matched_tools else "none"}',
            f'Permission denials: {len(denied_tools)}',
        ]
        output = self._format_output(summary_lines)
        projected_usage = self.total_usage.add_turn(prompt, output)
        stop_reason = 'completed'
        if projected_usage.input_tokens + projected_usage.output_tokens > self.config.max_budget_tokens:
            stop_reason = 'max_budget_reached'
        self.mutable_messages.append(prompt)
        self.transcript_store.append(prompt)
        self.permission_denials.extend(denied_tools)
        self.total_usage = projected_usage
        self.compact_messages_if_needed()
        return TurnResult(
            prompt=prompt,
            output=output,
            matched_commands=matched_commands,
            matched_tools=matched_tools,
            permission_denials=denied_tools,
            usage=self.total_usage,
            stop_reason=stop_reason,
        )

    def stream_submit_message(
        self,
        prompt: str,
        matched_commands: tuple[str, ...] = (),
        matched_tools: tuple[str, ...] = (),
        denied_tools: tuple[PermissionDenial, ...] = (),
    ):
        """Пошагово публикует события обработки сообщения.

        Параметры:
        - `prompt`: текст сообщения пользователя.
        - `matched_commands`: предварительно сопоставленные команды.
        - `matched_tools`: предварительно сопоставленные инструменты.
        - `denied_tools`: отказы по правам, которые требуется отразить в потоке.

        Возвращает:
        - Генератор словарей событий в порядке `message_start`,
          промежуточных событий и `message_stop`.
        """

        yield {'type': 'message_start', 'session_id': self.session_id, 'prompt': prompt}
        if matched_commands:
            yield {'type': 'command_match', 'commands': matched_commands}
        if matched_tools:
            yield {'type': 'tool_match', 'tools': matched_tools}
        if denied_tools:
            yield {'type': 'permission_denial', 'denials': [denial.tool_name for denial in denied_tools]}
        result = self.submit_message(prompt, matched_commands, matched_tools, denied_tools)
        yield {'type': 'message_delta', 'text': result.output}
        yield {
            'type': 'message_stop',
            'usage': {'input_tokens': result.usage.input_tokens, 'output_tokens': result.usage.output_tokens},
            'stop_reason': result.stop_reason,
            'transcript_size': len(self.transcript_store.entries),
        }

    def compact_messages_if_needed(self) -> None:
        """Ограничивает объем хранимой истории в памяти и транскрипте."""

        if len(self.mutable_messages) > self.config.compact_after_turns:
            self.mutable_messages[:] = self.mutable_messages[-self.config.compact_after_turns :]
        self.transcript_store.compact(self.config.compact_after_turns)

    def replay_user_messages(self) -> tuple[str, ...]:
        """Возвращает пользовательские сообщения, сохраненные в транскрипте."""

        return self.transcript_store.replay()

    def flush_transcript(self) -> None:
        """Помечает транскрипт как сброшенный для последующей персистентности."""

        self.transcript_store.flush()

    def persist_session(self) -> str:
        """Сохраняет активную сессию в файловое хранилище.

        Возвращает:
        - Путь к созданному JSON-файлу сессии.
        """

        self.flush_transcript()
        path = save_session(
            StoredSession(
                session_id=self.session_id,
                messages=tuple(self.mutable_messages),
                input_tokens=self.total_usage.input_tokens,
                output_tokens=self.total_usage.output_tokens,
            )
        )
        return str(path)

    def _format_output(self, summary_lines: list[str]) -> str:
        """Преобразует внутреннюю сводку в текстовый или JSON-ответ."""

        if self.config.structured_output:
            payload = {
                'summary': summary_lines,
                'session_id': self.session_id,
            }
            return self._render_structured_output(payload)
        return '\n'.join(summary_lines)

    def _render_structured_output(self, payload: dict[str, object]) -> str:
        """Сериализует структурированный ответ с ограниченным числом повторов."""

        last_error: Exception | None = None
        for _ in range(self.config.structured_retry_limit):
            try:
                return json.dumps(payload, indent=2)
            except (TypeError, ValueError) as exc:  # pragma: no cover - defensive branch
                last_error = exc
                payload = {'summary': ['structured output retry'], 'session_id': self.session_id}
        raise RuntimeError('structured output rendering failed') from last_error

    def render_summary(self) -> str:
        """Формирует Markdown-сводку по Python-рабочему пространству.

        Возвращает:
        - Текст Markdown со сведениями о manifest, command surface, tool
          surface и текущем состоянии сессии.

        Пример:
        ```python
        summary = QueryEnginePort.from_workspace().render_summary()
        print(summary)
        ```
        """

        command_backlog = build_command_backlog()
        tool_backlog = build_tool_backlog()
        sections = [
            '# Python Porting Workspace Summary',
            '',
            self.manifest.to_markdown(),
            '',
            f'Command surface: {len(command_backlog.modules)} mirrored entries',
            *command_backlog.summary_lines()[:10],
            '',
            f'Tool surface: {len(tool_backlog.modules)} mirrored entries',
            *tool_backlog.summary_lines()[:10],
            '',
            f'Session id: {self.session_id}',
            f'Conversation turns stored: {len(self.mutable_messages)}',
            f'Permission denials tracked: {len(self.permission_denials)}',
            f'Usage totals: in={self.total_usage.input_tokens} out={self.total_usage.output_tokens}',
            f'Max turns: {self.config.max_turns}',
            f'Max budget tokens: {self.config.max_budget_tokens}',
            f'Transcript flushed: {self.transcript_store.flushed}',
        ]
        return '\n'.join(sections)
