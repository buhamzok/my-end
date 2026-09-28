from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Text, Float
from sqlalchemy.orm import sessionmaker, declarative_base
from .config import DB_URL
from . import voice as V
from triage import AgeGroup, Severity, Symptom, SymptomReport, decide
engine = create_engine(DB_URL, connect_args={"check_same_thread":False} if DB_URL.startswith("sqlite") else {})
Session = sessionmaker(bind=engine)
Base = declarative_base()
class Ticket(Base):
    __tablename__="tickets"
    id=Column(Integer,primary_key=True)
    caller=Column(String,default="")
    lang=Column(String,default="en")
    symptoms=Column(Text,default="")
    tier=Column(String,default="self_care")
    reason=Column(Text,default="")
    confidence=Column(Float,default=0)
    status=Column(String,default="open")
Base.metadata.create_all(engine)
app = FastAPI(title="Voice Triage Intake")
app.add_middleware(CORSMiddleware,allow_origins=["*"],allow_methods=["*"],allow_headers=["*"])
class IntakeIn(BaseModel):
    caller: str=""; lang: str="en"; symptoms: list[str]=[]; flags: dict={}
class StatusIn(BaseModel):
    status: str
def _report(symptoms, flags):
    """Free-text symptom names + flags -> SymptomReport for the rules engine."""
    r=SymptomReport(); aliases={"diarrhea":"diarrhoea","seizure":"convulsions","high_fever":"fever"}
    for x in symptoms:
        k=x.lower().strip().replace(" ","_"); k=aliases.get(k,k)
        if k in Symptom._value2member_map_: r.add_symptoms([Symptom(k)])
        elif k: r.other_notes.append(x)
    if flags.get("duration_days") is not None: r.duration_days=int(flags["duration_days"])
    if flags.get("severe"): r.severity=Severity.SEVERE
    if flags.get("age_group") in AgeGroup._value2member_map_: r.age_group=AgeGroup(flags["age_group"])
    if flags.get("pregnant") is not None: r.pregnant=bool(flags["pregnant"])
    return r
def _save(caller, lang, report, decision):
    reason="; ".join(f"{i}: {why}" for i,why in zip(decision.matched_rule_ids,decision.reasons))
    db=Session(); t=Ticket(caller=caller,lang=lang or "en",symptoms=",".join([x.value for x in report.symptoms]+report.other_notes),tier=decision.tier.value,reason=reason,confidence=0)
    db.add(t); db.commit(); db.refresh(t); db.close()
    return t
@app.post("/api/intake")
def intake(b: IntakeIn):
    report=_report(b.symptoms,b.flags); decision=decide(report)
    t=_save(b.caller,b.lang,report,decision); tier,reason,conf=t.tier,t.reason,t.confidence
    action={"emergency":"nearest facility + alert","urgent":"CHW callback ticket","self_care":"TTS self-care advice"}[tier]
    return {"id":t.id,"tier":tier,"reason":reason,"confidence":conf,"action":action}
@app.get("/api/tickets")
def lst():
    db=Session()
    rows=db.query(Ticket).order_by(Ticket.id.desc()).all(); db.close()
    order={"emergency":0,"urgent":1,"self_care":2}
    return sorted([{"id":r.id,"caller":r.caller,"lang":r.lang,"symptoms":r.symptoms,"tier":r.tier,"reason":r.reason,"confidence":r.confidence,"status":r.status} for r in rows],key=lambda x:order[x["tier"]])
@app.post("/api/tickets/{tid}")
def set_status(tid:int,b:StatusIn):
    db=Session(); t=db.query(Ticket).get(tid)
    if not t: raise HTTPException(404,"no ticket")
    t.status=b.status; db.commit(); db.close(); return {"ok":True}
@app.post("/voice", response_class=Response)
def voice_cb(sessionId: str=Form(""), callerNumber: str=Form(""), dtmfDigits: str=Form(""), recordingUrl: str=Form(""), isActive: str=Form("1")):
    s=V.get(sessionId)
    if isActive=="0":
        if s and s.get("lang") and not s.get("done"):  # hung up mid-intake: still leave a ticket for a health worker
            s["done"]=True; _save(s["phone"],s["lang"],*V.finish(s))
        return Response(content="",media_type="application/xml")
    if not s:
        s,reply,act=V.start(callerNumber or "",sessionId or None)
        return Response(content=V.render(reply,act),media_type="application/xml")
    text=None
    if recordingUrl:
        try: text=V.transcribe(recordingUrl,s["lang"] if s["lang"] in ("en","sw") else None) or None
        except Exception as e: print("transcription failed:",e)
    reply,act,result=V.turn(s,text=text,digits=dtmfDigits or None)
    if result: _save(s["phone"],s["lang"],*result)
    to="+256700300001" if act=="transfer" else ""
    return Response(content=V.render(reply or "",act,to),media_type="application/xml")
@app.get("/health")
def health(): return {"ok":True}
