# Med-Intake (Next.js + FastAPI) — ported from SavaWatch
Stack: FastAPI + SQLite/Postgres tickets, Next.js dashboard, AT Voice `/voice`, rules engine decides tier.
Run BE: `pip install -r requirements.txt && uvicorn app.main:app --reload --app-dir backend` (port 8000)
Run FE: `cd frontend && npm i && NEXT_PUBLIC_API=http://localhost:8000 npm run dev`
AT Voice callback -> `https://<tunnel>/voice`. Endpoints: POST /api/intake, GET /api/tickets, POST /api/tickets/{id}, POST /voice.
