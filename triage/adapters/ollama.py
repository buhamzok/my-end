"""LLMClient for a model served locally by Ollama (https://ollama.com).

The request pins the output to the ``LLMTurn`` JSON schema (Ollama structured
outputs), so the model cannot produce malformed JSON and the harness rarely
needs a retry. Standard library only.
"""

from __future__ import annotations

import json
import urllib.request

from triage.llm import Message
from triage.schema import LLMTurn


class OllamaClient:
    def __init__(
        self,
        model: str = "qwen3:8b",
        host: str = "http://localhost:11434",
        *,
        temperature: float = 0.2,
        timeout: float = 20.0,
        think: bool | None = False,
        keep_alive: str = "30m",
    ):
        """``think=False`` turns off reasoning mode on models that have one (Qwen3),
        which is what keeps latency low. Pass ``None`` to leave the field out for
        models that reject it."""
        self.model = model
        self.url = host.rstrip("/") + "/api/chat"
        self.temperature = temperature
        self.timeout = timeout
        self.think = think
        self.keep_alive = keep_alive
        self._schema = LLMTurn.model_json_schema()

    def complete(self, system: str, messages: list[Message]) -> str:
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, *messages],
            "format": self._schema,
            "stream": False,
            "keep_alive": self.keep_alive,
            "options": {"temperature": self.temperature},
        }
        if self.think is not None:
            body["think"] = self.think
        request = urllib.request.Request(
            self.url,
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            payload = json.loads(response.read().decode())
        return payload["message"]["content"]
