from backend.stt import SpeechStartedEvent, TranscriptEvent, parse_deepgram


def test_final_result_with_confidence() -> None:
    ev = parse_deepgram(
        {
            "type": "Results",
            "is_final": True,
            "speech_final": True,
            "channel": {
                "alternatives": [
                    {"transcript": "where is my order ord 101", "confidence": 0.98}
                ]
            },
        }
    )
    assert isinstance(ev, TranscriptEvent)
    assert ev.text == "where is my order ord 101"
    assert ev.confidence == 0.98
    assert ev.is_final is True


def test_interim_result() -> None:
    ev = parse_deepgram(
        {
            "type": "Results",
            "is_final": False,
            "channel": {"alternatives": [{"transcript": "where is", "confidence": 0.7}]},
        }
    )
    assert isinstance(ev, TranscriptEvent)
    assert ev.is_final is False
    assert ev.text == "where is"


def test_speech_started_event() -> None:
    ev = parse_deepgram({"type": "SpeechStarted", "channel_index": [0]})
    assert isinstance(ev, SpeechStartedEvent)


def test_utterance_end_ignored() -> None:
    assert parse_deepgram({"type": "UtteranceEnd", "when": "2026-10-24T10:00:00"}) is None


def test_metadata_and_unknown_types_ignored() -> None:
    assert parse_deepgram({"type": "Metadata", "transaction_key": "x"}) is None
    assert parse_deepgram({"type": "Something"}) is None


def test_empty_alternatives_ignored() -> None:
    assert parse_deepgram({"type": "Results", "channel": {"alternatives": []}}) is None


def test_missing_confidence_is_none() -> None:
    ev = parse_deepgram(
        {"type": "Results", "is_final": True, "channel": {"alternatives": [{"transcript": "hi"}]}}
    )
    assert isinstance(ev, TranscriptEvent)
    assert ev.confidence is None
