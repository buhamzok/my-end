import pytest

from triage import AgeGroup, Severity, Symptom as S, SymptomReport, UrgencyTier, decide
from triage.rules import RULES

E, U, SC = UrgencyTier.EMERGENCY, UrgencyTier.URGENT, UrgencyTier.SELF_CARE


def report(*symptoms, **fields):
    return SymptomReport(symptoms=list(symptoms), **fields)


RULE_CASES = [
    (report(S.CONVULSIONS), "EM_CONVULSIONS", E),
    (report(S.UNCONSCIOUS), "EM_UNCONSCIOUS", E),
    (report(S.DIFFICULTY_BREATHING), "EM_BREATHING", E),
    (report(S.CHEST_PAIN), "EM_CHEST_PAIN", E),
    (report(S.SEVERE_BLEEDING), "EM_SEVERE_BLEEDING", E),
    (report(S.BLEEDING_IN_PREGNANCY), "EM_PREGNANCY_BLEEDING", E),
    (report(S.UNABLE_TO_DRINK), "EM_UNABLE_TO_DRINK", E),
    (report(S.VOMITING_EVERYTHING), "EM_VOMITS_EVERYTHING", E),
    (report(S.FEVER, S.STIFF_NECK), "EM_FEVER_STIFF_NECK", E),
    (report(S.FEVER, age_group=AgeGroup.INFANT), "UR_INFANT_FEVER", U),
    (report(S.FEVER, duration_days=2), "UR_FEVER_2_DAYS", U),
    (report(S.FEVER, S.RASH), "UR_FEVER_RASH", U),
    (report(S.FEVER, age_group=AgeGroup.ELDERLY), "UR_ELDERLY_FEVER", U),
    (report(S.BLOOD_IN_STOOL), "UR_BLOOD_IN_STOOL", U),
    (report(S.DIARRHOEA, duration_days=14), "UR_PERSISTENT_DIARRHOEA", U),
    (report(S.DIARRHOEA, S.VOMITING, age_group=AgeGroup.CHILD), "UR_YOUNG_DIARRHOEA_VOMITING", U),
    (report(S.COUGH, S.FAST_BREATHING), "UR_FAST_BREATHING", U),
    (report(S.HEADACHE, severity=Severity.SEVERE), "UR_SEVERE", U),
    (report(S.HEADACHE, pregnant=True), "UR_PREGNANT", U),
    (report(S.COUGH, duration_days=7), "UR_LONG_DURATION", U),
    (report(), "UR_NO_DATA", U),
    (report(S.RUNNY_NOSE, intake_complete=False), "UR_INCOMPLETE_INTAKE", U),
    (report(other_notes=["itchy eyes"]), "UR_UNRECOGNISED", U),
]


@pytest.mark.parametrize("r, rule_id, tier", RULE_CASES)
def test_each_rule(r, rule_id, tier):
    decision = decide(r)
    assert rule_id in decision.matched_rule_ids
    assert decision.tier == tier


def test_every_rule_is_covered_by_a_test():
    ids = {rule.id for rule in RULES}
    tested = {rule_id for _, rule_id, _ in RULE_CASES}
    assert ids == tested


def test_mild_symptoms_are_self_care():
    decision = decide(report(S.RUNNY_NOSE, S.SORE_THROAT, duration_days=1, severity=Severity.MILD))
    assert decision.tier == SC
    assert decision.matched_rule_ids == ["SC_DEFAULT"]


def test_highest_tier_wins_and_all_matches_are_listed():
    decision = decide(report(S.FEVER, S.CONVULSIONS, duration_days=3))
    assert decision.tier == E
    assert decision.matched_rule_ids == ["EM_CONVULSIONS", "UR_FEVER_2_DAYS"]
    assert len(decision.reasons) == 2


def test_short_fever_in_adult_is_self_care():
    assert decide(report(S.FEVER, duration_days=1, age_group=AgeGroup.ADULT)).tier == SC
