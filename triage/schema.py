"""Data contracts shared by the harness, the rules engine and the backend.

Everything the LLM is allowed to produce is described by ``LLMTurn``. Everything
the backend stores is described by ``IntakeOutcome``. The urgency tier only ever
appears on ``TriageDecision``, which is produced by the rules engine.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class Symptom(str, Enum):
    """Closed symptom vocabulary. The LLM must map what the caller says onto these."""

    FEVER = "fever"
    COUGH = "cough"
    DIFFICULTY_BREATHING = "difficulty_breathing"
    FAST_BREATHING = "fast_breathing"
    CHEST_PAIN = "chest_pain"
    CONVULSIONS = "convulsions"
    UNCONSCIOUS = "unconscious"
    UNABLE_TO_DRINK = "unable_to_drink"
    VOMITING_EVERYTHING = "vomiting_everything"
    VOMITING = "vomiting"
    DIARRHOEA = "diarrhoea"
    BLOOD_IN_STOOL = "blood_in_stool"
    SEVERE_BLEEDING = "severe_bleeding"
    BLEEDING_IN_PREGNANCY = "bleeding_in_pregnancy"
    STIFF_NECK = "stiff_neck"
    HEADACHE = "headache"
    RASH = "rash"
    ABDOMINAL_PAIN = "abdominal_pain"
    SORE_THROAT = "sore_throat"
    RUNNY_NOSE = "runny_nose"
    BODY_ACHES = "body_aches"
    EAR_PAIN = "ear_pain"
    PAINFUL_URINATION = "painful_urination"
    INJURY = "injury"


class AgeGroup(str, Enum):
    INFANT = "infant"  # under 1 year
    CHILD = "child"  # 1 to 12 years
    ADULT = "adult"
    ELDERLY = "elderly"  # 65 and over


class Severity(str, Enum):
    MILD = "mild"
    MODERATE = "moderate"
    SEVERE = "severe"


class UrgencyTier(str, Enum):
    SELF_CARE = "self_care"
    URGENT = "urgent"
    EMERGENCY = "emergency"

    @property
    def rank(self) -> int:
        return _TIER_RANK[self]


_TIER_RANK = {UrgencyTier.SELF_CARE: 0, UrgencyTier.URGENT: 1, UrgencyTier.EMERGENCY: 2}


class CloseReason(str, Enum):
    COMPLETED = "completed"  # model gathered enough and set done
    RED_FLAG = "red_flag"  # input guard found a danger sign
    OFF_TOPIC = "off_topic"  # caller kept drifting
    TURN_LIMIT = "turn_limit"  # hard cap on turns reached
    MODEL_FAILURE = "model_failure"  # LLM kept failing the output guard
    CALLER_HANGUP = "caller_hangup"  # finalize() called before the session closed itself


def _split_symptoms(values: Any) -> tuple[list[Symptom], list[str]]:
    """Keep recognised symptom codes; return unrecognised ones separately."""
    known, unknown = [], []
    for value in values or []:
        try:
            symptom = Symptom(str(value).strip().lower())
        except ValueError:
            unknown.append(str(value))
            continue
        if symptom not in known:
            known.append(symptom)
    return known, unknown


class LLMTurn(BaseModel):
    """The JSON object the model must return on every turn."""

    reply: str
    on_topic: bool
    symptoms: list[Symptom] = Field(default_factory=list)
    duration_days: int | None = Field(default=None, ge=0)
    severity: Severity | None = None
    age_group: AgeGroup | None = None
    pregnant: bool | None = None
    other_notes: str | None = None
    done: bool = False

    @field_validator("symptoms", mode="before")
    @classmethod
    def _drop_unknown_symptoms(cls, value: Any) -> list[Symptom]:
        # An invented symptom code should not throw away the whole turn.
        known, _ = _split_symptoms(value)
        return known


class SymptomReport(BaseModel):
    """Everything gathered about the caller so far. Input to the rules engine."""

    symptoms: list[Symptom] = Field(default_factory=list)
    duration_days: int | None = None
    severity: Severity | None = None
    age_group: AgeGroup | None = None
    pregnant: bool | None = None
    other_notes: list[str] = Field(default_factory=list)
    red_flag_phrases: list[str] = Field(default_factory=list)
    # False when the call ended before intake finished (hang-up, drift, turn cap,
    # model failure) or the keypad menu was not fully answered.
    intake_complete: bool = True

    def has(self, *symptoms: Symptom) -> bool:
        return any(s in self.symptoms for s in symptoms)

    def add_symptoms(self, symptoms: list[Symptom]) -> None:
        for symptom in symptoms:
            if symptom not in self.symptoms:
                self.symptoms.append(symptom)

    def merge(self, turn: LLMTurn) -> None:
        """Fold one model turn into the report. Later non-empty values win."""
        self.add_symptoms(turn.symptoms)
        for field in ("duration_days", "severity", "age_group", "pregnant"):
            value = getattr(turn, field)
            if value is not None:
                setattr(self, field, value)
        if turn.other_notes and turn.other_notes.strip():
            self.other_notes.append(turn.other_notes.strip())


class TriageDecision(BaseModel):
    tier: UrgencyTier
    matched_rule_ids: list[str]
    reasons: list[str]


class TurnResult(BaseModel):
    reply_text: str  # what the voice layer should say next
    done: bool  # hang up / stop listening once this is spoken
    emergency: bool = False  # red flag hit: route immediately
    outcome: IntakeOutcome | None = None  # set once the session has closed


class IntakeOutcome(BaseModel):
    report: SymptomReport
    decision: TriageDecision
    closed_reason: CloseReason
    turns: int
    transcript: list[dict[str, str]]

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe dict, ready to store as a ticket."""
        return self.model_dump(mode="json")


TurnResult.model_rebuild()
