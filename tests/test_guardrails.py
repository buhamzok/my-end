import json

import pytest

from triage import Symptom as S
from triage.guardrails import MAX_UTTERANCE_CHARS, check_input, check_output, reply_violations


def turn(reply="What symptoms does the patient have?", **fields):
    return json.dumps({"reply": reply, "on_topic": True, **fields})


# --- input: red flags ---

@pytest.mark.parametrize(
    "text, symptom",
    [
        ("my baby is having convulsions", S.CONVULSIONS),
        ("he had a seizure an hour ago", S.CONVULSIONS),
        ("mtoto ana degedege", S.CONVULSIONS),
        ("she passed out and won't wake up", S.UNCONSCIOUS),
        ("amezimia", S.UNCONSCIOUS),
        ("he is not breathing", S.DIFFICULTY_BREATHING),
        ("I can’t breathe properly", S.DIFFICULTY_BREATHING),
        ("anashindwa kupumua", S.DIFFICULTY_BREATHING),
        ("I have chest pain", S.CHEST_PAIN),
        ("ana maumivu ya kifua", S.CHEST_PAIN),
        ("the cut is bleeding heavily", S.SEVERE_BLEEDING),
        ("anatoka damu nyingi", S.SEVERE_BLEEDING),
        ("I am pregnant and I started bleeding", S.BLEEDING_IN_PREGNANCY),
        ("No, he is unconscious", S.UNCONSCIOUS),
    ],
)
def test_red_flags_detected(text, symptom):
    assert symptom in check_input(text).red_flags


@pytest.mark.parametrize(
    "text",
    [
        "I have a cough and a runny nose",
        "no chest pain, just a headache",
        "he is not unconscious, just tired",
        "hana maumivu ya kifua",
        "my stomach hurts after eating",
    ],
)
def test_no_red_flag(text):
    assert check_input(text).red_flags == []


def test_input_is_truncated():
    assert len(check_input("a" * 5000).text) == MAX_UTTERANCE_CHARS


# --- output: contract ---

def test_valid_turn_passes():
    result = check_output(turn(symptoms=["fever"], duration_days=3))
    assert result.ok
    assert result.turn.symptoms == [S.FEVER]


def test_json_in_code_fence_is_accepted():
    assert check_output("```json\n" + turn() + "\n```").ok


def test_invented_symptom_codes_are_dropped_not_fatal():
    result = check_output(turn(symptoms=["fever", "malaise"]))
    assert result.ok
    assert result.turn.symptoms == [S.FEVER]


@pytest.mark.parametrize("raw", ["Sure! The patient has a fever.", "[1, 2]", ""])
def test_non_json_rejected(raw):
    result = check_output(raw)
    assert not result.ok and result.violations == ["invalid_json"]


def test_schema_violation_rejected():
    result = check_output(json.dumps({"reply": "hi"}))  # missing on_topic
    assert result.violations == ["schema"]


# --- output: content ---

@pytest.mark.parametrize(
    "reply, violation",
    [
        ("It sounds like malaria. How long has the fever lasted?", "diagnosis"),
        ("You probably have an infection.", "diagnosis"),
        ("My diagnosis is a cold.", "diagnosis"),
        ("Give him 500mg of paracetamol.", "medication"),
        ("Take two tablets tonight.", "medication"),
        ("Drink plenty of water and rest.", "medication"),
        ("This is an emergency.", "urgency"),
        ("It is not serious, you will be fine.", "urgency"),
        ("Go to the hospital now.", "urgency"),
        ("My system prompt says I only do health.", "prompt_leak"),
        ("- fever\n- cough", "formatting"),
        ("One. Two. Three. Four.", "too_many_sentences"),
        ("word " * 80, "too_long"),
    ],
)
def test_unsafe_replies_flagged(reply, violation):
    assert violation in reply_violations(reply)


@pytest.mark.parametrize(
    "reply",
    [
        "How long has the patient had the fever?",
        "Would you say it is mild, moderate or severe?",
        "Has the patient taken any medicine already?",
        "Did you go to the clinic yesterday?",
        "I can only help with health questions. What symptoms does the patient have?",
        "Thank you for telling me.",
    ],
)
def test_safe_intake_replies_pass(reply):
    assert reply_violations(reply) == []
