from fastapi import FastAPI, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Text, Float
from sqlalchemy.orm import sessionmaker, declarative_base
from .config import DB_URL
from .triage_engine import triage
from . import voice as V
engine = create_engine(DB_URL, connect_args={"check_same_thread":False})
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
@app.post("/api/intake")
def intake(b: IntakeIn):
    tier,reason,conf=triage(b.symptoms,b.flags)
    db=Session(); t=Ticket(caller=b.caller,lang=b.lang,symptoms=",".join(b.symptoms),tier=tier,reason=reason,confidence=conf)
    db.add(t); db.commit(); db.refresh(t); db.close()
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
@app.post("/voice", response_class=str)
def voice_cb(sessionId: str=Form(""), callerNumber: str=Form(""), dtmfDigits: str=Form(""), recordingUrl: str=Form(""), isActive: str=Form("1")):
    from fastapi.responses import Response
    import requests as R
    if isActive=="0": return Response(content="",media_type="application/xml")
    s=V.get(sessionId)
    if not s:
        s,reply,act=V.start(callerNumber or "",sessionId or None)
        return Response(content=V.render(reply,act),media_type="application/xml")
    text=None
    if recordingUrl:
        try: text=" ".join([]) or None
        except Exception: pass
    tr,reply,act=V.turn(s,text=text,digits=dtmfDigits or None)
    if act=="triage":
        tier,reason,conf=triage(s["symptoms"],s["flags"])
        db=Session(); t=Ticket(caller=s["phone"],lang=s["lang"],symptoms=",".join(s["symptoms"]),tier=tier,reason=reason,confidence=conf)
        db.add(t); db.commit(); db.close()
        msg=f"Ticket {t.id}, {tier}. {reason}." if tier!="self_care" else f"{tier}. Rest, fluids, seek care if worse."
        return Response(content=V.render(msg,"hangup"),media_type="application/xml")
    to="+256700300001" if act=="transfer" else ""
    return Response(content=V.render(reply or "",act,to),media_type="application/xml")
@app.get("/health")
def health(): return {"ok":True}
