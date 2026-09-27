from triage import AgeGroup, Symptom as S, UrgencyTier, decide, report_from_keypresses
from triage.dtmf import MENU


def test_keypresses_build_a_report():
    r = report_from_keypresses({"age_group": "2", "fever": "1", "cough": "2", "duration": "3"})
    assert r.age_group == AgeGroup.CHILD
    assert r.symptoms == [S.FEVER]
    assert r.duration_days == 6
    assert decide(r).tier == UrgencyTier.URGENT


def test_complete_menu_with_mild_answers_is_self_care():
    answers = {q.id: "2" for q in MENU}
    answers.update(age_group="3", cough="1", duration="1", severity="1")
    r = report_from_keypresses(answers)
    assert r.intake_complete
    assert decide(r).tier == UrgencyTier.SELF_CARE


def test_partial_menu_is_not_complete():
    r = report_from_keypresses({"cough": "1"})
    assert not r.intake_complete
    assert decide(r).tier == UrgencyTier.URGENT


def test_pregnant_and_heavy_bleeding_is_emergency():
    r = report_from_keypresses({"pregnant": "1", "severe_bleeding": "1"})
    assert S.BLEEDING_IN_PREGNANCY in r.symptoms
    assert decide(r).tier == UrgencyTier.EMERGENCY


def test_invalid_keys_are_noted_not_guessed():
    r = report_from_keypresses({"fever": "7", "bogus": "1"})
    assert r.symptoms == []
    assert len(r.other_notes) == 2
    assert decide(r).tier == UrgencyTier.URGENT  # engine can't assess: health worker reviews


def test_every_yes_no_question_maps_to_a_symptom():
    special = {"age_group", "duration", "severity", "pregnant"}
    for question in MENU:
        if question.id not in special:
            S(question.id)
