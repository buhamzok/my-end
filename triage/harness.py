"""Per-call intake session: the model's leash.

One ``IntakeSession`` per phone call. The voice layer feeds it each transcribed
caller utterance and speaks back ``TurnResult.reply_text``. Once ``done`` is
true, ``outcome`` holds the ticket to store.

Order of defences on every turn:
1. Input guard: danger-sign keywords close the call as an emergency, no model call.
   A danger sign the model extracts later closes the call the same way.
2. Model call with the system prompt; caller speech is wrapped as data.
3. Output guard: invalid or unsafe replies get one corrective retry, then a
   canned safe line. Valid extraction is kept even when the reply is replaced.
4. Drift policy: repeated off-topic turns end the call; a hard turn cap ends it too.
5. The urgency tier always comes from the rules engine, never from the model.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from triage import prompts
from triage.guardrails import OutputCheck, check_input, check_output
from triage.llm import LLMClient, Message
from triage.rules.engine import decide
from triage.schema import (
    CloseReason,
    IntakeOutcome,
    LLMTurn,
    SymptomReport,
    TurnResult,
    UrgencyTier,
)

log = logging.getLogger(__name__)


class IntakeSession:
    def __init__(
        self,
        llm: LLMClient,
        *,
        clinic_name: str = "the community health line",
        max_turns: int = 6,
        max_off_topic: int = 3,
        max_model_failures: int = 2,
    ):
        self.llm = llm
        self.system_prompt = prompts.build_system_prompt(clinic_name)
        self.max_turns = max_turns
        self.max_off_topic = max_off_topic
        self.max_model_failures = max_model_failures

        self.report = SymptomReport()
        self.turns = 0
        self.off_topic_streak = 0
        self.model_failure_streak = 0
        self.closed_reason: CloseReason | None = None
        self._history: list[Message] = []
        self._transcript: list[dict[str, str]] = []
        self._outcome: IntakeOutcome | None = None

    @property
    def done(self) -> bool:
        return self.closed_reason is not None

    def opening_line(self) -> str:
        self._transcript.append({"role": "assistant", "content": prompts.GREETING})
        return prompts.GREETING

    def handle_utterance(self, text: str) -> TurnResult:
        if self.done:
            return self._result(self._closing_line(self.finalize()))

        self.turns += 1
        checked = check_input(text)
        self._transcript.append({"role": "caller", "content": checked.text})

        if checked.red_flags:
            self.report.add_symptoms(checked.red_flags)
            self.report.red_flag_phrases.extend(checked.phrases)
            return self._close(CloseReason.RED_FLAG)

        user_content = prompts.wrap_utterance(checked.text)
        if self.turns >= self.max_turns:
            user_content += prompts.LAST_TURN_NOTE
        self._history.append({"role": "user", "content": user_content})

        turn = self._ask_model()
        if turn is None:
            self.model_failure_streak += 1
            if self.model_failure_streak >= self.max_model_failures:
                return self._close(CloseReason.MODEL_FAILURE)
            return self._speak(prompts.SAFE_REPLY)
        self.model_failure_streak = 0
        self.report.merge(turn)

        # A danger sign the keyword scan missed but the model extracted.
        if decide(self.report).tier == UrgencyTier.EMERGENCY:
            return self._close(CloseReason.RED_FLAG)

        if turn.on_topic:
            self.off_topic_streak = 0
        else:
            self.off_topic_streak += 1
            if self.off_topic_streak >= self.max_off_topic:
                return self._close(CloseReason.OFF_TOPIC)
            if self.off_topic_streak > 1:
                return self._speak(prompts.REDIRECT_FIRM, turn)

        if turn.done:
            return self._close(CloseReason.COMPLETED)
        if self.turns >= self.max_turns:
            return self._close(CloseReason.TURN_LIMIT)
        return self._speak(turn.reply, turn)

    def finalize(self) -> IntakeOutcome:
        """Close the session (if still open) and return the ticket. Idempotent."""
        if self._outcome is None:
            if self.closed_reason is None:
                self.closed_reason = CloseReason.CALLER_HANGUP
            self.report.intake_complete = self.closed_reason in (
                CloseReason.COMPLETED,
                CloseReason.RED_FLAG,
            )
            self._outcome = IntakeOutcome(
                report=self.report,
                decision=decide(self.report),
                closed_reason=self.closed_reason,
                turns=self.turns,
                transcript=list(self._transcript),
            )
        return self._outcome

    # --- internals ---

    def _ask_model(self) -> LLMTurn | None:
        """One call plus at most one corrective retry. Returns a safe turn or None."""
        first = self._call(self._history)
        if first.ok:
            return first.turn

        log.warning("model output rejected: %s", first.violations)
        retry_messages = self._history + [
            {"role": "assistant", "content": first.raw},
            {
                "role": "user",
                "content": prompts.CORRECTION_TEMPLATE.format(violations=", ".join(first.violations)),
            },
        ]
        second = self._call(retry_messages)
        if second.ok:
            return second.turn

        log.warning("model retry rejected: %s", second.violations)
        salvage = second.turn or first.turn
        if salvage is None:
            return None
        # The extraction validated; only the spoken reply was unsafe. Keep the data,
        # replace the words.
        return salvage.model_copy(update={"reply": prompts.SAFE_REPLY})

    def _call(self, messages: list[Message]) -> _Attempt:
        try:
            raw = self.llm.complete(self.system_prompt, messages)
        except Exception:
            log.exception("LLM call failed")
            return _Attempt("", OutputCheck(turn=None, violations=["llm_error"]))
        return _Attempt(raw, check_output(raw))

    def _speak(self, reply: str, turn: LLMTurn | None = None) -> TurnResult:
        # Keep the model's history consistent with what was actually said.
        stored = turn.model_copy(update={"reply": reply}) if turn else None
        self._history.append(
            {
                "role": "assistant",
                "content": stored.model_dump_json() if stored else json.dumps({"reply": reply}),
            }
        )
        self._transcript.append({"role": "assistant", "content": reply})
        return TurnResult(reply_text=reply, done=False)

    def _close(self, reason: CloseReason) -> TurnResult:
        self.closed_reason = reason
        outcome = self.finalize()
        line = self._closing_line(outcome)
        outcome.transcript.append({"role": "assistant", "content": line})
        return self._result(line)

    @staticmethod
    def _closing_line(outcome: IntakeOutcome) -> str:
        if outcome.closed_reason == CloseReason.OFF_TOPIC:
            return prompts.CLOSING_OFF_TOPIC
        return prompts.CLOSING_BY_TIER[outcome.decision.tier]

    def _result(self, line: str) -> TurnResult:
        outcome = self.finalize()
        return TurnResult(
            reply_text=line,
            done=True,
            emergency=outcome.decision.tier == UrgencyTier.EMERGENCY,
            outcome=outcome,
        )


@dataclass
class _Attempt:
    raw: str
    check: OutputCheck

    @property
    def ok(self) -> bool:
        return self.check.ok

    @property
    def turn(self) -> LLMTurn | None:
        return self.check.turn

    @property
    def violations(self) -> list[str]:
        return self.check.violations
