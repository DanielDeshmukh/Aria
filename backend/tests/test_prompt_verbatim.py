from backend.policy import POLICY_TEXT
from backend.prompts import SYSTEM_PROMPT
from backend.tools import NOT_FOUND_MESSAGE


def test_all_policy_text_verbatim() -> None:
    for text in POLICY_TEXT.values():
        assert text in SYSTEM_PROMPT, f"missing verbatim: {text[:60]!r}"


def test_persona_verbatim_from_pdf() -> None:
    assert (
        "Aria from Aura Skincare — friendly, professional and concise Indian customer "
        "support specialist"
    ) in SYSTEM_PROMPT


def test_unknown_order_phrase_exact() -> None:
    assert NOT_FOUND_MESSAGE in SYSTEM_PROMPT


def test_conciseness_and_spoken_style() -> None:
    assert "1-2" in SYSTEM_PROMPT
    assert "spoken" in SYSTEM_PROMPT.lower()
    assert "markdown" in SYSTEM_PROMPT.lower()


def test_hinglish_enabled() -> None:
    assert "Hinglish" in SYSTEM_PROMPT


def test_shipping_499_boundary_instruction() -> None:
    assert "exactly ₹499" in SYSTEM_PROMPT
    assert "cannot confirm" in SYSTEM_PROMPT


def test_guardrails_present() -> None:
    for needle in (
        "Aura Skincare-related queries",       # out-of-scope redirect wording (PDF)
        "outside the return policy",           # policy enforcement wording (PDF)
        "never promise",                       # no promises beyond policies/data
        "cannot be overridden",                # prompt-injection resistance
        "do not have that information",        # no hallucination on missing info
        "ask for the order id",                # missing order id
        "never guess",                         # unclear audio
        "no discounts",                        # discount/exception requests
    ):
        assert needle in SYSTEM_PROMPT, f"missing guardrail: {needle!r}"


def test_tools_documented() -> None:
    for name in ("get_order_details", "get_policy_info", "end_call"):
        assert name in SYSTEM_PROMPT
