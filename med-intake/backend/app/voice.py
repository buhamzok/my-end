"""Voice agent. Ported from SavaWatch voice.py: AT Voice XML + DTMF fallback + LLM extract slot."""
import re, uuid, requests
from xml.sax.saxutils import escape
from .config import LLM_BASE_URL, LLM_API_KEY, LLM_MODEL, LLM_TIMEOUT, VOICE_NAME, PUBLIC_URL
_sessions: dict = {}
LANG_MENU = "Press 1 for English, 2 for Kiswahili, 3 for Luganda menu."
DTMF_SYMPTOMS = {"1":"fever","2":"cough","3":"diarrhea","4":"chest pain","5":"difficulty breathing","0":"human"}
INTENTS = [("human",["human","agent","nurse","doctor","person"]),("symptom",["fever","cough","pain","bleed","breath","vomit","diarrhea"]),("bye",["bye","thank"]),]
def _keyword(text:str):
    t=" "+re.sub(r"[^a-z ]"," ",text.lower())+" "
    for n,ph in INTENTS:
        if any(p in t for p in ph): return n
    return "other"
def extract_symptoms(text:str)->dict:
    """LLM extract slot (OpenAI-compatible). Fallback: keyword flags."""
    if LLM_BASE_URL and LLM_MODEL:
        try:
            r=requests.post(LLM_BASE_URL.rstrip("/")+"/chat/completions",
                headers={"Authorization":f"Bearer {LLM_API_KEY}"} if LLM_API_KEY else {},
                timeout=LLM_TIMEOUT, json={"model":LLM_MODEL,"temperature":0,"max_tokens":100,
                "messages":[{"role":"system","content":"Extract symptoms as JSON: {symptoms:[], severe:bool, duration_days:int}. No diagnosis."},
                {"role":"user","content":text}]})
            import json; return json.loads(r.json()["choices"][0]["message"]["content"])
        except Exception as e: print("llm extract fail, rules fallback:",e)
    return {"symptoms":[p for _,ph in INTENTS for p in ph if p in text.lower()],"severe":any(w in text.lower() for w in ["severe","heavy","cannot","unconscious"]),"duration_days":0}
def _say(t:str):
    return f'<Say voice="{VOICE_NAME}">{escape(t)}</Say>'
def render(reply:str,action:str,transfer_to:str=""):
    if action=="listen":
        body=f'<Record finishOnKey="#" maxLength="15" timeout="5" playBeep="true">{_say(reply+" Speak after beep, press hash.")}</Record>'
    elif action=="menu":
        body=f'<GetDigits numDigits="1" timeout="10" finishOnKey="#">{_say(reply)}</GetDigits>'
    elif action=="transfer":
        body=_say(reply)+f'<Dial phoneNumbers="{escape(transfer_to)}" record="true" sequential="true"/>'
    else: body=_say(reply)
    return '<?xml version="1.0" encoding="UTF-8"?><Response>'+body+"</Response>"
def start(phone,sid=None):
    sid=sid or uuid.uuid4().hex[:12]
    s={"sid":sid,"phone":phone,"lang":None,"symptoms":[],"flags":{}}
    _sessions[sid]=s
    return s, "Welcome. "+LANG_MENU, "menu"
def turn(s,text=None,digits=None):
    if not s.get("lang"):
        m={"1":"en","2":"sw","3":"luganda"}.get((digits or "")[:1])
        if not m: return None,"Sorry. "+LANG_MENU,"menu"
        s["lang"]=m
        if m=="luganda":
            return None,"Luganda menu. Press 1 fever, 2 cough, 3 diarrhea, 4 chest pain, 5 breathing difficulty, 0 nurse.","menu"
        return None,"Describe symptoms after beep.","listen"
    if s["lang"]=="luganda":
        sym=DTMF_SYMPTOMS.get((digits or "")[:1])
        if not sym: return None,"Press 1-5 symptom, 0 nurse.","menu"
        if sym=="human": return None,"Connecting to nurse.","transfer"
        s["symptoms"].append(sym); return sym,None,"triage"
    if digits=="0": return None,"Connecting to nurse.","transfer"
    d=extract_symptoms(text or ""); s["symptoms"]+=d.get("symptoms",[]); s["flags"]={**s["flags"],**{k:v for k,v in d.items() if k!="symptoms"}}
    return text,None,"triage"
def get(sid): return _sessions.get(sid)
