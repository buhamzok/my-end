"""LLM intake harness and rules-based triage engine."""

from triage.dtmf import MENU as DTMF_MENU, report_from_keypresses
from triage.harness import IntakeSession
from triage.llm import FakeLLMClient, LLMClient
from triage.rules.engine import decide
from triage.schema import (
    AgeGroup,
    CloseReason,
    IntakeOutcome,
    LLMTurn,
    Severity,
    Symptom,
    SymptomReport,
    TriageDecision,
    TurnResult,
    UrgencyTier,
)

__all__ = [
    "AgeGroup",
    "CloseReason",
    "DTMF_MENU",
    "FakeLLMClient",
    "IntakeOutcome",
    "IntakeSession",
    "LLMClient",
    "LLMTurn",
    "Severity",
    "Symptom",
    "SymptomReport",
    "TriageDecision",
    "TurnResult",
    "UrgencyTier",
    "decide",
    "report_from_keypresses",
]
