"""Provider-agnostic LLM interface.

The harness only needs one method. Wrap whichever provider the team picks, for
example::

    class MyClient:
        def complete(self, system, messages):
            # messages: [{"role": "user" | "assistant", "content": str}, ...]
            resp = sdk.create(system=system, messages=messages, max_tokens=400)
            return resp.text

Ask the provider for JSON output if it supports it; the harness validates the
result either way.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, Protocol

Message = dict[str, str]


class LLMClient(Protocol):
    def complete(self, system: str, messages: list[Message]) -> str:
        """Return the model's raw text for this conversation."""
        ...


Scripted = str | dict[str, Any] | Callable[[str, list[Message]], str] | Exception


class FakeLLMClient:
    """Replays scripted responses in order. For tests and offline demos.

    Each scripted item can be a raw string, a dict (sent as JSON), a callable
    ``(system, messages) -> str``, or an exception to raise.
    """

    def __init__(self, responses: list[Scripted]):
        self._responses = list(responses)
        self.calls: list[tuple[str, list[Message]]] = []

    def complete(self, system: str, messages: list[Message]) -> str:
        self.calls.append((system, [dict(m) for m in messages]))
        if not self._responses:
            raise RuntimeError("FakeLLMClient ran out of scripted responses")
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        if callable(item):
            return item(system, messages)
        if isinstance(item, dict):
            return json.dumps(item)
        return item
