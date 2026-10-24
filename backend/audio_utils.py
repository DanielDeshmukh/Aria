"""PCM16 helpers for the voice pipeline (mono linear16, base64 on the wire)."""

from __future__ import annotations

import base64
from array import array


def resample_pcm16(pcm: bytes, src_rate: int, dst_rate: int) -> bytes:
    """Linear-interpolation resample of little-endian PCM16 audio."""
    if src_rate == dst_rate or not pcm:
        return pcm
    samples = array("h")
    samples.frombytes(pcm)
    if not samples:
        return b""
    out_len = int(len(samples) * dst_rate / src_rate)
    step = src_rate / dst_rate
    last = len(samples) - 1
    out = array("h")
    for i in range(out_len):
        pos = i * step
        idx = int(pos)
        if idx >= last:
            out.append(samples[last])
            continue
        frac = pos - idx
        value = samples[idx] + (samples[idx + 1] - samples[idx]) * frac
        out.append(int(round(value)))
    return out.tobytes()


def pcm16_to_b64(pcm: bytes) -> str:
    return base64.b64encode(pcm).decode("ascii")


def b64_to_pcm16(data: str) -> bytes:
    return base64.b64decode(data)
