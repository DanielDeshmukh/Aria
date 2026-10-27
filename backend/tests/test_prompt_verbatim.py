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


def test_english_default_language_rule() -> None:
    """Live repro: an English customer got a Hinglish reply. English is the
    default and sticky — only the customer's latest message switches it."""
    for needle in (
        "reply in English by default",
        "LATEST message",
        "Never answer an English message in Hindi or Hinglish",
        "the moment they write English, you reply in English again",
    ):
        assert needle in SYSTEM_PROMPT, f"missing language rule: {needle!r}"


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
    for name in ("get_order_details", "cancel_order", "get_policy_info", "end_call"):
        assert name in SYSTEM_PROMPT


def test_cancellation_confirmation_flow() -> None:
    """Fix 3 + issue 2: eligibility is checked FIRST, ineligible orders are
    denied without any confirmation question, and only a Processing order
    goes read back -> explicit yes -> cancel_order(confirmed=true). The agent
    never claims a cancellation the tool did not return."""
    for needle in (
        "check eligibility FIRST",
        "do NOT ask any confirmation question",
        "never ask for confirmation on an order that cannot be cancelled",
        "ask whether they want it cancelled",
        "wait for an explicit yes",
        "confirmed=true",
        "confirmed=false never cancels",
        "NEVER say an order is cancelled unless cancel_order returned cancelled=true",
        "NOT_CONFIRMED",
    ):
        assert needle in SYSTEM_PROMPT, f"missing confirmation gate: {needle!r}"


def test_order_id_discipline_after_runbook() -> None:
    """Runbook scenarios 5/9/11: invented 'ORD-099' example in a reply, tool
    calls on 'Order'/'just now' — all stay explicitly forbidden."""
    for needle in (
        "CALL it whenever the customer's words contain any digits",
        'no digits at all (e.g. "just now", "Order", "?")',
        "Never guess an id (e.g. ORD-099)",
        'no "it might be ORD-099"',
    ):
        assert needle in SYSTEM_PROMPT, f"missing id discipline: {needle!r}"


def test_closing_offer_discipline() -> None:
    """Production bug: Aria appended "Is there anything else I can help you
    with?" to almost every reply — including right after her own question
    ("...cancel it for you? Is there anything else...?"). The offer is capped
    at once per RESOLVED REQUEST (relaxed from once per call: each new
    customer message opens a new request), only after a fully resolved
    request, and never in the same reply as a question to the customer; every
    other reply ends without it (the idle nudge handles silence). The quoted
    wording must survive for session._CLOSING_OFFER_RE (quiet-end window)."""
    for needle in (
        "Is there anything else I can help you with?",  # quiet-end detector phrase
        "AT MOST ONCE per resolved request",           # rule 2: per resolved request
        "fully resolves the customer's request",        # rule 2: only after resolution
        "never append it to every reply",               # rule 2: not on every reply
        "NEVER put the closing offer in the same reply as a question to the customer",
        "a confirmation question, a request for an order id or a clarification",
        "finish after your answer and stop",
    ):
        assert needle in SYSTEM_PROMPT, f"missing closing-offer rule: {needle!r}"
    # the old always-append instruction is gone, and the offer is quoted once
    assert "close with one offer" not in SYSTEM_PROMPT
    assert "After you have answered" not in SYSTEM_PROMPT
    # the once-per-call cap was relaxed to per resolved request
    assert "AT MOST ONCE in the whole call" not in SYSTEM_PROMPT
    assert SYSTEM_PROMPT.count("Is there anything else I can help you with?") == 1


def test_brevity_no_volunteering_and_goodbye_wrap_up() -> None:
    """Log findings: chatty replies. Answer only what was asked — never
    volunteer shipping fees or eligibility — the cancel-eligible confirmation
    is one short question without restating the policy, and a customer
    goodbye is wrapped up with a one-line farewell + end_call()."""
    for needle in (
        "1-2 short sentences",                          # max two short sentences
        "Answer only what the customer asked",
        "never volunteer shipping fees",
        "the confirmation is ONE short question",       # cancel-eligible, no restating
        "one short goodbye line, then call end_call()", # goodbye -> end_call
    ):
        assert needle in SYSTEM_PROMPT, f"missing brevity rule: {needle!r}"
