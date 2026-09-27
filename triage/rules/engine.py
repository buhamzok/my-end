"""Deterministic triage: SymptomReport in, TriageDecision out. No LLM involved."""

from __future__ import annotations

from triage.rules.rules import RULES, SELF_CARE_REASON, Rule
from triage.schema import SymptomReport, TriageDecision, UrgencyTier


def decide(report: SymptomReport, rules: list[Rule] | None = None) -> TriageDecision:
    """Evaluate every rule and return the highest tier matched.

    All matching rules are listed (for the audit trail), not only the ones at the
    winning tier. With no match the tier is self-care.
    """
    matched = [rule for rule in (RULES if rules is None else rules) if rule.when(report)]
    if not matched:
        return TriageDecision(
            tier=UrgencyTier.SELF_CARE,
            matched_rule_ids=["SC_DEFAULT"],
            reasons=[SELF_CARE_REASON],
        )
    tier = max((rule.tier for rule in matched), key=lambda t: t.rank)
    return TriageDecision(
        tier=tier,
        matched_rule_ids=[rule.id for rule in matched],
        reasons=[rule.reason for rule in matched],
    )
