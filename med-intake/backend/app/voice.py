"""Voice agent. Ported from SavaWatch voice.py: AT Voice XML + DTMF fallback + LLM extract slot."""
import io, re, sys, uuid, requests
from pathlib import Path
from xml.sax.saxutils import escape
from .config import LLM_BASE_URL, LLM_API_KEY, LLM_MODEL, LLM_TIMEOUT, VOICE_NAME, PUBLIC_URL, ASR_MODEL, ASR_DEVICE
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # repo root: the triage/ package
from triage import IntakeSession, decide, report_from_keypresses, UrgencyTier
from triage.adapters import OllamaClient
from triage.dtmf import MENU
from triage.prompts import CLOSING_BY_TIER
LLM = OllamaClient(LLM_MODEL or "qwen3:8b", re.sub(r"/v1/?$", "", LLM_BASE_URL or "http://localhost:11434"), timeout=LLM_TIMEOUT)
_sessions: dict = {}
LANG_MENU = "Press 1 for English, 2 for Kiswahili, 3 for Luganda menu."
INTENTS = [("human",["human","agent","nurse","doctor","person"]),("symptom",["fever","cough","pain","bleed","breath","vomit","diarrhea"]),("bye",["bye","thank"]),]
def _keyword(text:str):
    t=" "+re.sub(r"[^a-z ]"," ",text.lower())+" "
    for n,ph in INTENTS:
        if any(p in t for p in ph): return n
    return "other"
_asr = None
def transcribe(recording_url:str, lang:str|None)->str:
    """Download the AT recording and run faster-whisper on it (model loaded once)."""
    global _asr
    if _asr is None:
        from faster_whisper import WhisperModel
        _asr=WhisperModel(ASR_MODEL, device=ASR_DEVICE, compute_type="float16" if ASR_DEVICE=="cuda" else "int8")
    audio=requests.get(recording_url, timeout=10).content
    segments,_=_asr.transcribe(io.BytesIO(audio), language=lang, beam_size=1, vad_filter=True, condition_on_previous_text=False)
    return " ".join(x.text.strip() for x in segments).strip()
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
    s={"sid":sid,"phone":phone,"lang":None,"intake":IntakeSession(LLM),"keys":{},"q":0}
    _sessions[sid]=s
    return s, "Welcome. "+LANG_MENU, "menu"
def _menu_prompt(s): return MENU[s["q"]].prompt+" Press 0 for a nurse."
def turn(s,text=None,digits=None):
    """Returns (reply, action, result). result is (report, decision) once the call is finished."""
    if not s.get("lang"):
        m={"1":"en","2":"sw","3":"luganda"}.get((digits or "")[:1])
        if not m: return "Sorry. "+LANG_MENU,"menu",None
        s["lang"]=m
        if m=="luganda":
            return "Luganda menu. "+_menu_prompt(s),"menu",None
        return "Describe symptoms after beep.","listen",None
    if s["lang"]=="luganda":
        d=(digits or "")[:1]
        if d=="0": return "Connecting to nurse.","transfer",None
        q=MENU[s["q"]]
        if d not in q.options: return "Sorry. "+_menu_prompt(s),"menu",None
        s["keys"][q.id]=d; s["q"]+=1
        report=report_from_keypresses(s["keys"]); decision=decide(report)
        if decision.tier==UrgencyTier.EMERGENCY or s["q"]>=len(MENU):
            s["done"]=True
            return CLOSING_BY_TIER[decision.tier],"hangup",(report,decision)
        return _menu_prompt(s),"menu",None
    if digits=="0": return "Connecting to nurse.","transfer",None
    if not text: return "Sorry, I did not catch that.","listen",None
    r=s["intake"].handle_utterance(text)
    if not r.done: return r.reply_text,"listen",None
    s["done"]=True
    return r.reply_text,"hangup",(r.outcome.report,r.outcome.decision)
def finish(s):
    """(report, decision) for a call that ended before intake finished, e.g. caller hung up."""
    if s.get("lang")=="luganda":
        report=report_from_keypresses(s["keys"]); return report,decide(report)
    o=s["intake"].finalize(); return o.report,o.decision
def get(sid): return _sessions.get(sid)
