"""
scripts/phase6_speech_regression.py

WHAT THIS IS FOR:
Automated regression test runner for F.R.I.D.A.Y. v2 Phase 6 Speech Director policy.
Exercises the 12 core conversational scenarios specified in Runbook §22 and verifies:
  1. SpeechDecision (emotion, intensity, delivery, tags)
  2. Rendered TTS text with private bracket tags
  3. Resolved acoustic condition key (neutral/master fallback for disabled)
  4. Calibrated blend weight
  5. Fallback safety (no crying->sigh, no serious->angry, no empathy->sigh, no surprise->gasp)
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

from friday.interaction.speech_director import SpeechContext, SpeechDirector


@dataclass
class RegressionScenario:
    name: str
    input_text: str
    context: SpeechContext
    expected_emotion: str
    expected_delivery: str
    expected_tags: tuple[str, ...]
    expected_condition: str
    expected_blend_weight: float | None = None
    forbidden_tags: tuple[str, ...] = ()
    forbidden_conditions: tuple[str, ...] = ()


REGRESSION_SCENARIOS = [
    # 1. Ordinary factual response
    RegressionScenario(
        name="ordinary factual response",
        input_text="The temperature outside is twenty two degrees.",
        context=SpeechContext(),
        expected_emotion="neutral",
        expected_delivery="conversational",
        expected_tags=(),
        expected_condition="neutral",
        expected_blend_weight=0.65,
    ),
    # 2. Successful completion
    RegressionScenario(
        name="successful completion",
        input_text="The backup completed successfully.",
        context=SpeechContext(task_status="COMPLETED"),
        expected_emotion="satisfied",
        expected_delivery="confident",
        expected_tags=("happy",),
        expected_condition="happy",
        expected_blend_weight=0.65,
        forbidden_tags=("sigh", "chuckle"),
    ),
    # 3. Failure
    RegressionScenario(
        name="failure",
        input_text="Unfortunately, the request failed.",
        context=SpeechContext(task_status="FAILED"),
        expected_emotion="empathetic",
        expected_delivery="soft",
        expected_tags=(),
        expected_condition="neutral",
        expected_blend_weight=0.65,
        forbidden_tags=("sigh", "chuckle", "laugh"),
        forbidden_conditions=("sigh", "angry"),
    ),
    # 4. Apology
    RegressionScenario(
        name="apology",
        input_text="I'm sorry, Boss. I couldn't complete that operation.",
        context=SpeechContext(task_status="FAILED"),
        expected_emotion="empathetic",
        expected_delivery="soft",
        expected_tags=(),
        expected_condition="neutral",
        expected_blend_weight=0.65,
        forbidden_tags=("sigh",),
        forbidden_conditions=("sigh",),
    ),
    # 5. Confirmation prompt
    RegressionScenario(
        name="confirmation",
        input_text="I need your confirmation before I continue.",
        context=SpeechContext(awaiting_confirmation=True),
        expected_emotion="calm",
        expected_delivery="clear",
        expected_tags=(),
        expected_condition="neutral",
        expected_blend_weight=0.65,
    ),
    # 6. Surprise
    RegressionScenario(
        name="surprise",
        input_text="That's unexpected. The service is already running.",
        context=SpeechContext(),
        expected_emotion="surprised",
        expected_delivery="measured",
        expected_tags=(),
        expected_condition="neutral",
        expected_blend_weight=0.65,
        forbidden_tags=("gasp", "surprised"),
        forbidden_conditions=("surprised",),
    ),
    # 7. Greeting
    RegressionScenario(
        name="greeting",
        input_text="Good morning, Boss. Everything is ready.",
        context=SpeechContext(),
        expected_emotion="warm",
        expected_delivery="cheerful",
        expected_tags=("happy",),
        expected_condition="happy",
        expected_blend_weight=0.65,
        forbidden_tags=("chuckle",),
    ),
    # 8. Thinking
    RegressionScenario(
        name="thinking",
        input_text="Let me check that for you.",
        context=SpeechContext(),
        expected_emotion="thoughtful",
        expected_delivery="measured",
        expected_tags=(),
        expected_condition="neutral",
        expected_blend_weight=0.65,
    ),
    # 9. Humorous context
    RegressionScenario(
        name="humorous context",
        input_text="Haha, that actually worked.",
        context=SpeechContext(),
        expected_emotion="amused",
        expected_delivery="playful",
        expected_tags=("laugh",),
        expected_condition="chuckle",
        expected_blend_weight=0.50,
        forbidden_tags=("chuckle",),
    ),
    # 10. Crying request (disabled)
    RegressionScenario(
        name="crying request",
        input_text="[crying] I'm here with you.",
        context=SpeechContext(),
        expected_emotion="empathetic",
        expected_delivery="soft",
        expected_tags=(),
        expected_condition="neutral",
        expected_blend_weight=0.65,
        forbidden_tags=("crying", "sigh"),
        forbidden_conditions=("sigh", "crying"),
    ),
    # 11. Angry request (disabled)
    RegressionScenario(
        name="angry request",
        input_text="[angry] Stop. That operation is not permitted.",
        context=SpeechContext(),
        expected_emotion="serious",
        expected_delivery="firm",
        expected_tags=(),
        expected_condition="neutral",
        expected_blend_weight=0.65,
        forbidden_tags=("angry",),
        forbidden_conditions=("angry",),
    ),
    # 12. Sarcastic request (disabled)
    RegressionScenario(
        name="sarcastic request",
        input_text="[sarcastic] Perfect. Exactly what we needed.",
        context=SpeechContext(),
        expected_emotion="sarcastic",
        expected_delivery="witty",
        expected_tags=(),
        expected_condition="neutral",
        expected_blend_weight=0.65,
        forbidden_tags=("sarcastic",),
        forbidden_conditions=("sarcastic",),
    ),
]


def run_regression() -> int:
    """Run all regression scenarios and output a structured report."""
    print("=" * 80)
    print("FRIDAY v2 Phase 6 Speech Director Policy Regression Suite")
    print("=" * 80)

    # Initialize Speech Director with default Phase 6 policy
    director = SpeechDirector(
        allow_vocal_effects=True,
        allow_experimental_emotion_tags=True,
        production_tags=["happy", "dramatic", "whispering"],
        limited_tags=["laugh"],
        disabled_tags=["chuckle", "sigh", "gasp", "sarcastic", "angry", "crying", "fear", "surprised"],
        expression_blend_weights={
            "happy": 0.65,
            "dramatic": 0.60,
            "whispering": 0.70,
            "laugh": 0.50,
        },
    )

    failures = 0
    passed = 0

    print(f"{'Scenario':<28} | {'Emotion':<11} | {'Tags':<10} | {'Condition':<10} | {'Weight':<6} | {'Result'}")
    print("-" * 80)

    for sc in REGRESSION_SCENARIOS:
        decision = director.decide(sc.input_text, context=sc.context)
        rendered = director.render(sc.input_text, context=sc.context)
        condition = director.get_condition_key(decision)
        blend_weight = director.get_blend_weight(decision)

        # Check assertions
        errors = []
        if decision.emotion != sc.expected_emotion:
            errors.append(f"emotion got '{decision.emotion}', expected '{sc.expected_emotion}'")
        if decision.delivery != sc.expected_delivery:
            errors.append(f"delivery got '{decision.delivery}', expected '{sc.expected_delivery}'")
        if decision.tags != sc.expected_tags:
            errors.append(f"tags got {decision.tags}, expected {sc.expected_tags}")
        if condition != sc.expected_condition:
            errors.append(f"condition got '{condition}', expected '{sc.expected_condition}'")
        if sc.expected_blend_weight is not None and abs(blend_weight - sc.expected_blend_weight) > 0.01:
            errors.append(f"blend_weight got {blend_weight}, expected {sc.expected_blend_weight}")

        # Check forbidden tags
        for ft in sc.forbidden_tags:
            if ft in decision.tags:
                errors.append(f"forbidden tag '{ft}' emitted")
            if f"[{ft}]" in rendered:
                errors.append(f"forbidden tag '[{ft}]' rendered in text")

        # Check forbidden condition routing
        for fc in sc.forbidden_conditions:
            if condition == fc:
                errors.append(f"forbidden condition '{fc}' resolved")

        tags_str = str(list(decision.tags)) if decision.tags else "()"
        if not errors:
            passed += 1
            print(f"{sc.name:<28} | {decision.emotion:<11} | {tags_str:<10} | {condition:<10} | {blend_weight:<6.2f} | PASS")
        else:
            failures += 1
            print(f"{sc.name:<28} | {decision.emotion:<11} | {tags_str:<10} | {condition:<10} | {blend_weight:<6.2f} | FAIL")
            for err in errors:
                print(f"    -> ERROR: {err}")

    # Safety checks
    print("-" * 80)
    print("Running Safety & Invariance Checks...")

    # A. Safety: laugh blocked in ERROR state
    err_dec = director.decide("Haha error happened", context=SpeechContext(task_status="ERROR"))
    err_rend = director.render("[laugh] Error message", context=SpeechContext(task_status="ERROR"))
    if "laugh" in err_dec.tags or "[laugh]" in err_rend:
        failures += 1
        print("FAIL: Laugh tag permitted in ERROR task status!")
    else:
        passed += 1
        print("PASS: Laugh tag strictly blocked in ERROR task status.")

    # B. Idempotence: render(render(t)) == render(t)
    sample_text = "Good morning, Boss. Everything is ready."
    once = director.render(sample_text)
    twice = director.render(once)
    if once == twice and once.count("[happy]") == 1:
        passed += 1
        print("PASS: Tag injection is strictly idempotent.")
    else:
        failures += 1
        print("FAIL: Idempotence check failed!")

    # C. Semantic preservation: words unchanged
    import re
    cleaned = re.sub(r"^(?:\[[\w\s-]+\]\s*)+", "", once).strip()
    if "Good morning, Boss. Everything is ready." in cleaned:
        passed += 1
        print("PASS: Semantic text content perfectly preserved.")
    else:
        failures += 1
        print("FAIL: Semantic text was altered!")

    print("=" * 80)
    print(f"Results: {passed} passed, {failures} failed out of {passed + failures} checks.")
    print("=" * 80)

    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(run_regression())
