import io
import json

import pytest

from triage import IntakeSession, LLMTurn, Symptom as S
from triage.adapters import OllamaClient


@pytest.fixture
def fake_ollama(monkeypatch):
    requests = []
    replies = []

    def urlopen(request, timeout):
        requests.append((request, json.loads(request.data), timeout))
        content = json.dumps(replies.pop(0))
        return io.BytesIO(json.dumps({"message": {"role": "assistant", "content": content}}).encode())

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    return requests, replies


def test_request_shape(fake_ollama):
    requests, replies = fake_ollama
    replies.append({"reply": "How long?", "on_topic": True})
    client = OllamaClient("qwen3:8b", "http://gpu-box:11434/", temperature=0.1, timeout=5)

    out = client.complete("SYSTEM", [{"role": "user", "content": "hi"}])

    request, body, timeout = requests[0]
    assert request.full_url == "http://gpu-box:11434/api/chat"
    assert timeout == 5
    assert body["model"] == "qwen3:8b"
    assert body["messages"][0] == {"role": "system", "content": "SYSTEM"}
    assert body["messages"][1] == {"role": "user", "content": "hi"}
    assert body["format"] == LLMTurn.model_json_schema()
    assert body["think"] is False
    assert body["stream"] is False
    assert body["options"]["temperature"] == 0.1
    assert json.loads(out)["reply"] == "How long?"


def test_think_can_be_omitted(fake_ollama):
    requests, replies = fake_ollama
    replies.append({"reply": "Hello.", "on_topic": True})
    OllamaClient("gemma3:12b", think=None).complete("S", [])
    assert "think" not in requests[0][1]


def test_harness_turn_through_adapter(fake_ollama):
    _, replies = fake_ollama
    replies.append({"reply": "How many days?", "on_topic": True, "symptoms": ["cough"]})
    session = IntakeSession(OllamaClient())
    assert session.handle_utterance("I have a cough").reply_text == "How many days?"
    assert session.report.symptoms == [S.COUGH]


def test_server_down_falls_back_safely(monkeypatch):
    def urlopen(request, timeout):
        raise OSError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    result = IntakeSession(OllamaClient()).handle_utterance("I have a cough")
    assert not result.done
    assert "tell me more" in result.reply_text
