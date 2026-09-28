"""Rules-based triage engine. LLM never decides tier. WHO/IMCI-style."""
from typing import Literal
Tier = Literal["emergency","urgent","self_care"]
EMERGENCY = {"chest pain","difficulty breathing","severe bleeding","unconscious","labour","seizure","stroke"}
URGENT = {"high fever","dehydration","persistent vomiting","severe pain","fever","cough","diarrhea"}
def triage(symptoms: list[str], flags: dict) -> tuple[Tier,str,int]:
    s = {x.lower().strip() for x in symptoms}
    if flags.get("emergency_flag") or (s & EMERGENCY and flags.get("severe",False)):
        return "emergency","Emergency keywords + severity -> immediate routing",95
    if s & EMERGENCY:
        return "emergency","Emergency keyword match",90
    if flags.get("urgent_flag") or (s & URGENT and (flags.get("duration_days",0)>=3 or flags.get("severe"))):
        return "urgent","Urgent symptom + duration/severity -> CHW callback",80
    if s & URGENT:
        return "urgent","Urgent symptom match",70
    return "self_care","No red flags -> self-care advice",60
