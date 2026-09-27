"""Keypress path for languages without reliable speech recognition.

A native speaker records one audio prompt per question below. The caller
answers with the keypad, and the answers become the same ``SymptomReport`` the
LLM path produces, so both paths go through the same rules engine.
"""

from __future__ import annotations

from dataclasses import dataclass

from triage.schema import AgeGroup, Severity, Symptom, SymptomReport

YES, NO = "1", "2"


@dataclass(frozen=True)
class MenuQuestion:
    id: str
    prompt: str  # English script for the recording
    options: dict[str, object]  # keypress -> value


def _yes_no(question_id: str, prompt: str) -> MenuQuestion:
    return MenuQuestion(question_id, f"{prompt} Press 1 for yes, 2 for no.", {YES: True, NO: False})


# Asked in this order. Danger signs come first so an emergency is caught early.
MENU: list[MenuQuestion] = [
    MenuQuestion(
        "age_group",
        "Who is sick? Press 1 for a baby under one year, 2 for a child, 3 for an adult, "
        "4 for an older person over 65.",
        {"1": AgeGroup.INFANT, "2": AgeGroup.CHILD, "3": AgeGroup.ADULT, "4": AgeGroup.ELDERLY},
    ),
    _yes_no("convulsions", "Is the patient having fits or convulsions?"),
    _yes_no("unconscious", "Is the patient unconscious or very hard to wake?"),
    _yes_no("difficulty_breathing", "Is the patient struggling to breathe?"),
    _yes_no("severe_bleeding", "Is the patient bleeding heavily?"),
    _yes_no("unable_to_drink", "Is the patient unable to drink or breastfeed?"),
    _yes_no("chest_pain", "Does the patient have chest pain?"),
    _yes_no("pregnant", "Is the patient pregnant?"),
    _yes_no("fever", "Does the patient have a fever or feel hot?"),
    _yes_no("cough", "Does the patient have a cough?"),
    _yes_no("diarrhoea", "Does the patient have diarrhoea?"),
    _yes_no("blood_in_stool", "Is there blood in the stool?"),
    _yes_no("vomiting", "Is the patient vomiting?"),
    _yes_no("rash", "Does the patient have a rash?"),
    MenuQuestion(
        "duration",
        "How long has the patient been sick? Press 1 for less than a day, 2 for one to two days, "
        "3 for three to six days, 4 for one to two weeks, 5 for more than two weeks.",
        # Each band maps to its upper bound so duration rules err towards caution.
        {"1": 0, "2": 2, "3": 6, "4": 14, "5": 15},
    ),
    MenuQuestion(
        "severity",
        "How bad is it? Press 1 for mild, 2 for moderate, 3 for severe.",
        {"1": Severity.MILD, "2": Severity.MODERATE, "3": Severity.SEVERE},
    ),
]

_BY_ID = {q.id: q for q in MENU}


def report_from_keypresses(answers: dict[str, str]) -> SymptomReport:
    """Build a report from ``{question_id: key}``. Missing questions are unknown."""
    report = SymptomReport()
    for question_id, key in answers.items():
        question = _BY_ID.get(question_id)
        if question is None:
            report.other_notes.append(f"unknown menu question {question_id!r}")
            continue
        value = question.options.get(str(key).strip())
        if value is None:
            report.other_notes.append(f"invalid keypress {key!r} for {question_id}")
            continue
        if question_id == "age_group":
            report.age_group = value
        elif question_id == "duration":
            report.duration_days = value
        elif question_id == "severity":
            report.severity = value
        elif question_id == "pregnant":
            report.pregnant = value
        elif value is True:
            report.add_symptoms([Symptom(question_id)])

    report.intake_complete = all(q.id in answers for q in MENU) and not report.other_notes
    if report.pregnant and report.has(Symptom.SEVERE_BLEEDING):
        report.add_symptoms([Symptom.BLEEDING_IN_PREGNANCY])
    return report
