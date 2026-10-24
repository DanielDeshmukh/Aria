from array import array

from backend.audio_utils import b64_to_pcm16, pcm16_to_b64, resample_pcm16


def test_resample_48k_to_16k_yields_1600_samples() -> None:
    pcm = array("h", [0] * 4800).tobytes()
    out = resample_pcm16(pcm, 48000, 16000)
    assert len(out) == 1600 * 2


def test_resample_constant_signal_preserves_value() -> None:
    pcm = array("h", [1000] * 4800).tobytes()
    got = array("h")
    got.frombytes(resample_pcm16(pcm, 48000, 16000))
    assert len(got) == 1600
    assert all(abs(v - 1000) <= 1 for v in got)


def test_resample_upsample_length() -> None:
    pcm = array("h", [0] * 800).tobytes()
    out = resample_pcm16(pcm, 16000, 48000)
    assert len(out) // 2 == 2400


def test_resample_identity_when_rates_match() -> None:
    pcm = bytes(range(16))
    assert resample_pcm16(pcm, 16000, 16000) == pcm


def test_resample_empty_input() -> None:
    assert resample_pcm16(b"", 48000, 16000) == b""


def test_b64_round_trip() -> None:
    pcm = bytes(range(256))
    assert b64_to_pcm16(pcm16_to_b64(pcm)) == pcm
