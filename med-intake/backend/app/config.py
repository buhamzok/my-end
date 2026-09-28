"""Settings. Ported from SavaWatch config.py -> medical intake."""
import os
BASE = os.path.dirname(os.path.abspath(__file__))
def _load_env():
    f = os.path.join(os.path.dirname(BASE), ".env")
    if not os.path.exists(f): return
    for line in open(f, encoding="utf-8"):
        line=line.strip()
        if not line or line.startswith("#") or "=" not in line: continue
        k,v=line.split("=",1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
_load_env()
AT_USERNAME=os.getenv("AT_USERNAME","sandbox")
AT_API_KEY=os.getenv("AT_API_KEY","")
DRY_RUN=(not AT_API_KEY) or os.getenv("DRY_RUN","0")=="1"
DB_URL=os.getenv("DB_URL","sqlite:///./tickets.db")
PORT=int(os.getenv("PORT","8000"))
LLM_BASE_URL=os.getenv("LLM_BASE_URL","")
LLM_API_KEY=os.getenv("LLM_API_KEY","")
LLM_MODEL=os.getenv("LLM_MODEL","")
LLM_TIMEOUT=float(os.getenv("LLM_TIMEOUT","4"))
PUBLIC_URL=os.getenv("PUBLIC_URL","").rstrip("/")
VOICE_NAME=os.getenv("VOICE_NAME","woman")
