"""トラッカー系フォーマット向けの波形サンプル合成（サンプルベース音源）。

MIDI と異なり MOD/XM/IT/S3M/DMF はサンプル（PCM波形データ）を
プレイヤーがピッチ変換して再生する方式のため、Instrument.waveform に
応じた短い波形ループを実際に合成し、符号付き8bit PCM バイト列として
出力する。ドラム系はループさせず、減衰するワンショット波形にする。
"""

from __future__ import annotations

import math
import random
from typing import List

_MELODIC_LOOP_LEN = 128  # 音程楽器用ループの長さ（サンプル数）
_DRUM_LEN = 1024  # ドラム用ワンショットの長さ（サンプル数）


def _clamp8(v: float) -> int:
    v = max(-128.0, min(127.0, v))
    return int(round(v)) & 0xFF


def _sine(n: int, length: int) -> float:
    return math.sin(2 * math.pi * n / length)


def _square(n: int, length: int) -> float:
    return 1.0 if (n % length) < (length / 2) else -1.0


def _saw(n: int, length: int) -> float:
    phase = (n % length) / length
    return 2.0 * phase - 1.0


def _triangle(n: int, length: int) -> float:
    phase = (n % length) / length
    return 4.0 * abs(phase - 0.5) - 1.0


_WAVEFORM_FUNCS = {
    "sine": _sine,
    "square": _square,
    "saw": _saw,
    "triangle": _triangle,
}


def generate_melodic_sample(waveform: str, amplitude: float = 100.0,
                             length: int = _MELODIC_LOOP_LEN) -> bytes:
    """ループ可能な音程楽器用の1サイクル波形を合成する（符号付き8bit）。"""
    func = _WAVEFORM_FUNCS.get(waveform, _sine)
    data = bytearray(length)
    for n in range(length):
        data[n] = _clamp8(func(n, length) * amplitude)
    return bytes(data)


def generate_drum_sample(kind: str, rng: random.Random = None,
                          length: int = _DRUM_LEN) -> bytes:
    """減衰するワンショットのドラムサンプルを合成する（符号付き8bit）。

    Args:
        kind: "kick" | "snare" | "hihat"
    """
    rng = rng or random.Random(0)
    data = bytearray(length)

    if kind == "kick":
        # 低い周波数から急速に下降するサイン波（ピッチスウィープ）＋指数減衰
        start_freq = 130.0
        end_freq = 40.0
        phase = 0.0
        for n in range(length):
            t = n / length
            freq = start_freq + (end_freq - start_freq) * t
            phase += freq / length * 8.0
            envelope = math.exp(-4.0 * t)
            data[n] = _clamp8(math.sin(2 * math.pi * phase) * 120.0 * envelope)
    elif kind == "snare":
        for n in range(length):
            t = n / length
            envelope = math.exp(-6.0 * t)
            noise = rng.uniform(-1.0, 1.0)
            tone = math.sin(2 * math.pi * n * 180.0 / length)
            data[n] = _clamp8((noise * 0.75 + tone * 0.25) * 110.0 * envelope)
    else:  # hihat
        for n in range(length):
            t = n / length
            envelope = math.exp(-10.0 * t)
            noise = rng.uniform(-1.0, 1.0)
            data[n] = _clamp8(noise * 100.0 * envelope)

    return bytes(data)


def synthesize_for_instrument(instrument, rng: random.Random = None) -> bytes:
    """Instrument の役割・波形種別に応じたサンプルデータを合成する。"""
    if instrument.is_drum:
        kind = {"drum_kick": "kick", "drum_snare": "snare"}.get(instrument.role, "hihat")
        return generate_drum_sample(kind, rng=rng)
    return generate_melodic_sample(instrument.waveform)
