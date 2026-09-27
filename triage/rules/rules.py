"""Triage rules as data.

PLACEHOLDER CLINICAL CONTENT: these rules are loosely modelled on WHO IMCI
general danger signs and are for the hackathon demo only. They must be reviewed
and signed off by a clinician before any real-world use.

Each rule is independent. The engine evaluates all of them and takes the
highest tier matched, so adding a rule can only make a decision more cautious.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from triage.schema import AgeGroup, Severity, Symptom as S, SymptomReport, UrgencyTier

E, U = UrgencyTier.EMERGENCY, UrgencyTier.URGENT


@dataclass(frozen=True)
class Rule:
    id: str
    tier: UrgencyTier
    reason: str
    when: Callable[[SymptomReport], bool]


def _days_at_least(report: SymptomReport, days: int) -> bool:
    return report.duration_days is not None and report.duration_days >= days


def _young(report: SymptomReport) -> bool:
    return report.age_group in (AgeGroup.INFANT, AgeGroup.CHILD)


RULES: list[Rule] = [
    # --- Emergency: general danger signs ---
    Rule("EM_CONVULSIONS", E, "Convulsions or seizures", lambda r: r.has(S.CONVULSIONS)),
    Rule("EM_UNCONSCIOUS", E, "Unconscious or cannot be woken", lambda r: r.has(S.UNCONSCIOUS)),
    Rule("EM_BREATHING", E, "Difficulty breathing", lambda r: r.has(S.DIFFICULTY_BREATHING)),
    Rule("EM_CHEST_PAIN", E, "Chest pain", lambda r: r.has(S.CHEST_PAIN)),
    Rule("EM_SEVERE_BLEEDING", E, "Severe bleeding", lambda r: r.has(S.SEVERE_BLEEDING)),
    Rule(
        "EM_PREGNANCY_BLEEDING",
        E,
        "Bleeding during pregnancy",
        lambda r: r.has(S.BLEEDING_IN_PREGNANCY),
    ),
    Rule("EM_UNABLE_TO_DRINK", E, "Unable to drink or breastfeed", lambda r: r.has(S.UNABLE_TO_DRINK)),
    Rule("EM_VOMITS_EVERYTHING", E, "Vomiting everything", lambda r: r.has(S.VOMITING_EVERYTHING)),
    Rule("EM_FEVER_STIFF_NECK", E, "Fever with stiff neck", lambda r: r.has(S.FEVER) and r.has(S.STIFF_NECK)),
    # --- Urgent: needs a health worker soon ---
    Rule(
        "UR_INFANT_FEVER",
        U,
        "Fever in an infant",
        lambda r: r.has(S.FEVER) and r.age_group == AgeGroup.INFANT,
    ),
    Rule(
        "UR_FEVER_2_DAYS",
        U,
        "Fever for 2 days or more",
        lambda r: r.has(S.FEVER) and _days_at_least(r, 2),
    ),
    Rule("UR_FEVER_RASH", U, "Fever with rash", lambda r: r.has(S.FEVER) and r.has(S.RASH)),
    Rule(
        "UR_ELDERLY_FEVER",
        U,
        "Fever in an older adult",
        lambda r: r.has(S.FEVER) and r.age_group == AgeGroup.ELDERLY,
    ),
    Rule("UR_BLOOD_IN_STOOL", U, "Blood in stool", lambda r: r.has(S.BLOOD_IN_STOOL)),
    Rule(
        "UR_PERSISTENT_DIARRHOEA",
        U,
        "Diarrhoea for 14 days or more",
        lambda r: r.has(S.DIARRHOEA) and _days_at_least(r, 14),
    ),
    Rule(
        "UR_YOUNG_DIARRHOEA_VOMITING",
        U,
        "Diarrhoea with vomiting in a child (dehydration risk)",
        lambda r: _young(r) and r.has(S.DIARRHOEA) and r.has(S.VOMITING),
    ),
    Rule(
        "UR_FAST_BREATHING",
        U,
        "Fast breathing",
        lambda r: r.has(S.FAST_BREATHING),
    ),
    Rule("UR_SEVERE", U, "Caller describes symptoms as severe", lambda r: r.severity == Severity.SEVERE),
    Rule(
        "UR_PREGNANT",
        U,
        "Symptoms during pregnancy",
        lambda r: bool(r.pregnant) and bool(r.symptoms or r.other_notes),
    ),
    Rule(
        "UR_LONG_DURATION",
        U,
        "Symptoms for 7 days or more",
        lambda r: bool(r.symptoms or r.other_notes) and _days_at_least(r, 7),
    ),
    # --- Fail-safe: never send someone to self-care when we could not assess them ---
    Rule(
        "UR_NO_DATA",
        U,
        "No symptoms could be collected; a health worker should call back",
        lambda r: not r.symptoms and not r.other_notes,
    ),
    Rule(
        "UR_INCOMPLETE_INTAKE",
        U,
        "Intake did not finish; a health worker should call back",
        lambda r: not r.intake_complete,
    ),
    Rule(
        "UR_UNRECOGNISED",
        U,
        "Symptoms described are outside the engine's vocabulary; a health worker should review",
        lambda r: not r.symptoms and bool(r.other_notes),
    ),
]

SELF_CARE_REASON = "No danger signs or urgent criteria matched"
