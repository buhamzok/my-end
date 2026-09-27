"""Deterministic checks around the model.

``check_input`` runs on the caller's words before the model sees them and
catches danger signs, so an emergency never waits on (or depends on) the model.

``check_output`` runs on the model's raw text and rejects anything outside the
contract: bad JSON, a diagnosis, medication advice, an urgency judgement, a
leaked prompt, or a reply too long or too formatted to speak.

The keyword lists are intentionally broad: a false positive costs a retry or a
health-worker callback, a false negative could cost much more. The Swahili
phrases need review by a native speaker.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from pydantic import ValidationError

from triage.prompts import MAX_REPLY_CHARS
from triage.schema import LLMTurn, Symptom

MAX_UTTERANCE_CHARS = 1000
MAX_REPLY_SENTENCES = 3

# Appended to patterns that are fine inside a question ("Did you go to the
# clinic?") but not as a statement ("Go to the clinic.").
_NOT_QUESTION = r"(?![^.!?]*\?)"


def _compile(patterns: list[str]) -> list[re.Pattern[str]]:
    return [re.compile(p, re.IGNORECASE) for p in patterns]


def _normalise(text: str) -> str:
    return text.replace("’", "'").replace("‘", "'")


# --- Input side: red flags --------------------------------------------------

RED_FLAG_PATTERNS: dict[Symptom, list[re.Pattern[str]]] = {
    Symptom.CONVULSIONS: _compile([
        r"\bconvuls\w*",
        r"\bseizures?\b",
        r"\bseizing\b",
        r"\bfitting\b",
        r"\bhaving (a )?fits?\b",
        r"\bdegedege\b",
        r"\bkifafa\b",
    ]),
    Symptom.UNCONSCIOUS: _compile([
        r"\bunconscious\b",
        r"\bunresponsive\b",
        r"\bpassed out\b",
        r"\b(won't|will not|can't|cannot|can not) (be )?wak(e|en)\b",
        r"\bnot waking\b",
        r"\bamezimia\b",
        r"\bhajitambui\b",
        r"\bamepoteza fahamu\b",
    ]),
    Symptom.DIFFICULTY_BREATHING: _compile([
        r"\b(not|isn't|stopped|stop) breathing\b",
        r"\b(can't|cannot|can not|struggling to|hard to|trouble|difficulty|difficult to) breath(e|ing)?\b",
        r"\bgasping\b",
        r"\bchoking\b",
        r"\bhapumui\b",
        r"\b(kushindwa|anashindwa|shida ya) kupumua\b",
    ]),
    Symptom.CHEST_PAIN: _compile([
        r"\bchest pains?\b",
        r"\bpain in (my|his|her|the) chest\b",
        r"\bmaumivu ya kifua\b",
    ]),
    Symptom.SEVERE_BLEEDING: _compile([
        r"\b(heavy|heavily|severe|severely|a lot of|lots of) bleed\w*",
        r"\bbleed\w* (heavily|a lot|badly|severely)\b",
        r"\bbleed\w* (that )?(won't|will not|does not|doesn't) stop\b",
        r"\b(won't|will not) stop bleeding\b",
        r"\bdamu nyingi\b",
    ]),
    Symptom.BLEEDING_IN_PREGNANCY: _compile([
        r"\bpregnan\w*\b.{0,40}\bbleed\w*",
        r"\bbleed\w*.{0,40}\bpregnan\w*",
        r"\bmjamzito\b.{0,40}\bdamu\b",
        r"\bdamu\b.{0,40}\bmjamzito\b",
    ]),
}

# A red flag only counts as negated when the negation sits right before it
# ("no chest pain", "he is not unconscious"). "No, he is unconscious" still fires.
_NEGATED = re.compile(r"\b(no|not|never|without|hana|hakuna|sina)\s+(any\s+|a\s+)?$", re.IGNORECASE)


@dataclass
class InputCheck:
    text: str  # possibly truncated utterance to pass on
    red_flags: list[Symptom] = field(default_factory=list)
    phrases: list[str] = field(default_factory=list)


def check_input(text: str) -> InputCheck:
    text = _normalise(text or "").strip()[:MAX_UTTERANCE_CHARS]
    result = InputCheck(text=text)
    for symptom, patterns in RED_FLAG_PATTERNS.items():
        for pattern in patterns:
            match = next(
                (m for m in pattern.finditer(text) if not _NEGATED.search(text[: m.start()])),
                None,
            )
            if match:
                result.red_flags.append(symptom)
                result.phrases.append(match.group(0))
                break
    return result


# --- Output side: contract and content checks -------------------------------

OUTPUT_RULES: dict[str, list[re.Pattern[str]]] = {
    "diagnosis": _compile([
        r"\bdiagnos\w*",
        r"\byou (probably|likely|must|definitely|might|may|could) (have|be suffering)\b" + _NOT_QUESTION,
        r"\bsuffering from\b" + _NOT_QUESTION,
        r"\b(malaria|typhoid|pneumonia|tuberculosis|cholera|covid\w*|coronavirus|hiv|"
        r"meningitis|diabetes|hypertension|asthma|cancer|sepsis|dengue|measles|anaemia|anemia|"
        r"influenza|flu|infection|infected|ulcers?|\w+itis)\b",
        r"\btb\b",
    ]),
    "medication": _compile([
        r"\b\d+(\.\d+)?\s?(mg|mcg|ml|milligrams?|millilitres?|milliliters?)\b",
        r"\b(dose|doses|dosage|prescri\w*)\b",
        r"\b(take|give|use|try|buy|start|swallow)\b.{0,30}\b(tablets?|pills?|capsules?|medicines?|"
        r"medications?|drugs?|syrup|antibiotics?|painkillers?)\b",
        r"\b(paracetamol|panadol|acetaminophen|ibuprofen|aspirin|amoxicillin|coartem|artemether|"
        r"antibiotics?|ors|oral rehydration)\b",
        r"\b(drink (plenty|lots|more)|get (some |plenty of )?rest|home remed\w*)\b",
    ]),
    "urgency": _compile([
        r"\bemergenc\w*",
        r"\burgent\w*",
        r"\bnot (serious|dangerous|urgent)\b",
        r"\bnothing (serious|to worry)\b",
        r"\b(no need to|don't) (worry|panic)\b",
        r"\b(this|that|it|he|she)('s| is| sounds| seems| looks)( very| quite)? "
        r"(serious|dangerous|critical|mild|minor)\b" + _NOT_QUESTION,
        r"\bgo to (the |a )?(nearest )?(hospital|clinic|health facility|doctor)\b" + _NOT_QUESTION,
        r"\b(call|get) (an )?ambulance\b",
        r"\b(you|they|he|she)('ll| will) be (fine|ok|okay|alright|all right)\b",
        r"\bself[- ]care\b",
    ]),
    "prompt_leak": _compile([
        r"\bsystem prompt\b",
        r"\bhard rules?\b",
        r"caller_utterance",
        r"\bas an ai\b",
        r"\bmy instructions\b",
    ]),
    "formatting": _compile([
        r"(^|\n)\s*([-*#>]|\d+\.)\s",
        r"\*\*|`|\{|\}",
    ]),
}


@dataclass
class OutputCheck:
    turn: LLMTurn | None
    violations: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.turn is not None and not self.violations


def _extract_json(raw: str) -> str:
    text = raw.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end < start:
        return text
    return text[start : end + 1]


def reply_violations(reply: str) -> list[str]:
    reply = _normalise(reply).strip()
    violations = []
    if not reply:
        violations.append("empty_reply")
    if len(reply) > MAX_REPLY_CHARS:
        violations.append("too_long")
    if len([s for s in re.split(r"[.!?]+(?:\s+|$)", reply) if s.strip()]) > MAX_REPLY_SENTENCES:
        violations.append("too_many_sentences")
    for name, patterns in OUTPUT_RULES.items():
        if any(p.search(reply) for p in patterns):
            violations.append(name)
    return violations


def check_output(raw: str) -> OutputCheck:
    try:
        data = json.loads(_extract_json(raw or ""))
    except json.JSONDecodeError:
        return OutputCheck(turn=None, violations=["invalid_json"])
    if not isinstance(data, dict):
        return OutputCheck(turn=None, violations=["invalid_json"])
    try:
        turn = LLMTurn.model_validate(data)
    except ValidationError:
        return OutputCheck(turn=None, violations=["schema"])
    return OutputCheck(turn=turn, violations=reply_violations(turn.reply))
