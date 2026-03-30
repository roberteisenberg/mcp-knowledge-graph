"""Phase 5: Tracing infrastructure.

TracedClient wraps anthropic.Anthropic to record every LLM call.
Tool call spans are recorded separately by the eval runner.
"""

import time
from dataclasses import dataclass, field


@dataclass
class Span:
    """A single operation -- either an LLM call or a tool call."""

    kind: str  # "llm" or "tool"
    name: str  # model name or tool name
    input_tokens: int = 0
    output_tokens: int = 0
    start_time: float = 0.0
    end_time: float = 0.0
    tool_args: dict = field(default_factory=dict)
    tool_result: str = ""

    @property
    def latency_ms(self) -> float:
        return (self.end_time - self.start_time) * 1000


@dataclass
class Trace:
    """All spans for a single query."""

    query_id: int
    query: str
    phase: int
    spans: list[Span] = field(default_factory=list)
    answer: str = ""

    @property
    def llm_spans(self) -> list[Span]:
        return [s for s in self.spans if s.kind == "llm"]

    @property
    def tool_spans(self) -> list[Span]:
        return [s for s in self.spans if s.kind == "tool"]

    @property
    def total_input_tokens(self) -> int:
        return sum(s.input_tokens for s in self.llm_spans)

    @property
    def total_output_tokens(self) -> int:
        return sum(s.output_tokens for s in self.llm_spans)

    @property
    def total_latency_ms(self) -> float:
        if not self.spans:
            return 0.0
        return (self.spans[-1].end_time - self.spans[0].start_time) * 1000


class _MessagesProxy:
    """Intercepts messages.create() to record LLM spans."""

    def __init__(self, messages, spans: list[Span]):
        self._messages = messages
        self._spans = spans

    def create(self, **kwargs):
        start = time.time()
        response = self._messages.create(**kwargs)
        end = time.time()

        self._spans.append(Span(
            kind="llm",
            name=kwargs.get("model", "unknown"),
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            start_time=start,
            end_time=end,
        ))

        return response


class TracedClient:
    """Wraps anthropic.Anthropic to record every messages.create() call.

    Usage:
        client = anthropic.Anthropic()
        traced = TracedClient(client)
        # Use traced exactly like client -- traced.messages.create(...)
        # After queries, read traced.spans
    """

    def __init__(self, client):
        self._client = client
        self.spans: list[Span] = []
        self.messages = _MessagesProxy(client.messages, self.spans)

    def reset(self):
        """Clear recorded spans for the next query."""
        self.spans.clear()

    def __getattr__(self, name):
        return getattr(self._client, name)
