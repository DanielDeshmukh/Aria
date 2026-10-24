from backend.splitter import split_sentences


def test_no_terminal_punct_holds_buffer() -> None:
    assert split_sentences("Wait for m") == ([], "Wait for m")


def test_multiple_sentences_in_order_with_remainder() -> None:
    sents, rest = split_sentences("Hello there. How can I help? Today...")
    assert sents == ["Hello there.", "How can I help?", "Today..."]
    assert rest == ""


def test_partial_tail_after_complete_sentence() -> None:
    sents, rest = split_sentences("All done. Now let m")
    assert sents == ["All done."]
    assert rest == "Now let m"


def test_price_decimal_never_splits() -> None:
    sents, rest = split_sentences("The order is ₹499.00 as shown. Done.")
    assert sents == ["The order is ₹499.00 as shown.", "Done."]


def test_abbreviation_letter_period_letter_never_splits() -> None:
    sents, rest = split_sentences("Mr. Sharma will help you. Okay.")
    assert sents == ["Mr. Sharma will help you.", "Okay."]


def test_exclamation_and_repeated_terminators() -> None:
    sents, rest = split_sentences("Great news!! Yes... ")
    assert sents == ["Great news!!", "Yes..."]
    assert rest == ""


def test_empty_buffer() -> None:
    assert split_sentences("") == ([], "")


def test_streaming_accumulation_equivalent() -> None:
    buffer = ""
    emitted: list[str] = []
    for chunk in ["Your order is ", "out for deli", "very today. It should", " arrive by 6 PM."]:
        buffer += chunk
        sents, buffer = split_sentences(buffer)
        emitted.extend(sents)
    if buffer.strip():
        emitted.append(buffer.strip())
    assert emitted == [
        "Your order is out for delivery today.",
        "It should arrive by 6 PM.",
    ]
