# Med-Intake (Next.js + FastAPI) — ported from SavaWatch
Stack: FastAPI + SQLite/Postgres tickets, Next.js dashboard, AT Voice `/voice`, rules engine decides tier.
Run BE: `pip install -r requirements.txt && uvicorn app.main:app --reload --app-dir backend` (port 8000)
Run FE: `cd frontend && npm i && NEXT_PUBLIC_API=http://localhost:8000 npm run dev`
Triage: the backend uses the `triage/` package at the repo root (harness + rules engine); needs Ollama with `qwen3:8b` (`LLM_BASE_URL`/`LLM_MODEL`) and faster-whisper for recordings (`ASR_MODEL`/`ASR_DEVICE`).
AT Voice callback -> `https://<tunnel>/voice`. Endpoints: POST /api/intake, GET /api/tickets, POST /api/tickets/{id}, POST /voice.
