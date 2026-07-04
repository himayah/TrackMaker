"""DefleMask Module (.dmf) エクスポータ ―― 実験的・ベストエフォート実装。

【重要な注意】
DMFフォーマットは非公開仕様であり、有志によるリバースエンジニアリング
情報とバージョンごとの差異（DefleMaskのバージョンによりフィールド幅が
変化する）に依存している。加えて zlib 圧縮されたペイロード内部の構造は
対象システム（Genesis/SMS/GameBoy等）ごとに大きく異なる。

本実装は Game Boy システム（4チャンネル: SQ1/SQ2/WAVE/NOISE、
チップにエンベロープ機能を持たないシンプルな音源）を対象に、公知情報
から復元した構造でベストエフォートの出力を行うものであり、実機の
DefleMask/Furnace での動作を本環境では検証できていない。
他の出力形式（MIDI/MOD/S3M/XM/IT）と比べて信頼度が低いことを
利用者は理解した上で使用し、読み込めない場合は Furnace 等でのインポート
確認や、issue報告を行うことを推奨する。
"""

from __future__ import annotations

import struct
import zlib
from typing import List

from ..core.models import Song
from .channel_remix import remix_to_channels

_DMF_VERSION = 24  # DefleMask 0.12.x 相当と推定されるフォーマットバージョン
_SYSTEM_GAMEBOY = 0x05
_GB_CHANNELS = 4  # SQ1, SQ2, WAVE, NOISE


def _pstr(s: str) -> bytes:
    """長さプレフィックス付き文字列（1byte長 + ASCII本体）。"""
    encoded = s.encode("ascii", "replace")[:255]
    return bytes([len(encoded)]) + encoded


def _note_octave(midi_note: int) -> tuple:
    """MIDIノート番号を (note 1-12, octave) のDMF流表現へ変換する。"""
    note_in_oct = midi_note % 12
    octave = max(0, min(9, midi_note // 12 - 1))
    dmf_note = note_in_oct + 1 if note_in_oct != 0 else 12  # DMFはCを12として扱う慣習
    return dmf_note, octave


def _encode_pattern_channel(pattern, channel_index: int) -> bytes:
    """1チャンネル・1パターン分の行データをエンコードする（各セル固定8byte）。

    セル構成: note(2) octave(1) volume(2) effect_code(2) effect_param(2)
    instrument(2) = 11byte/行（本実装での簡略フォーマット）。
    """
    body = bytearray()
    events = pattern.rows.get(channel_index, [None] * pattern.length)
    for row in range(pattern.length):
        event = events[row] if row < len(events) else None
        if event is None or event.note is None:
            body += struct.pack("<hBhhhh", 0, 0, -1, -1, -1, -1)
            continue
        if event.note < 0:
            body += struct.pack("<hBhhhh", 100, 0, -1, -1, -1, -1)  # ノートオフ相当
            continue
        note_val, octave = _note_octave(event.note)
        volume = max(0, min(64, event.volume))
        instrument = event.instrument if event.instrument is not None else 0
        body += struct.pack("<hBhhhh", note_val, octave, volume, -1, -1, instrument)
    return bytes(body)


def export_dmf(song: Song, path: str) -> None:
    """Song を DefleMask (.dmf, Game Boy システム) として実験的に書き出す。"""
    song4 = remix_to_channels(song, _GB_CHANNELS)

    payload = bytearray()
    payload.append(_SYSTEM_GAMEBOY)
    payload += _pstr(song4.title)
    payload += _pstr("")  # 作者名（未指定）

    payload += bytes([4, 16])  # ハイライトA/B（表示用、再生には無関係）
    payload += bytes([0])  # TimeBase
    payload += bytes([max(1, min(255, song4.speed))])  # TickTime1
    payload += bytes([max(1, min(255, song4.speed))])  # TickTime2
    payload += bytes([1])  # FramesMode = 1（BPM/Speedベース）
    payload += bytes([0])  # UsingCustomHZ = 0
    payload += bytes([0, 0, 0])  # CustomHZ 値（未使用）

    rows_per_pattern = song4.rows_per_pattern
    payload += struct.pack("<I", rows_per_pattern)
    payload.append(len(song4.order))  # パターンマトリクスの行数

    # パターンマトリクス: 全チャンネル共通のオーダーを採用（内部モデルは
    # チャンネル間で単一のオーダーリストを共有するため）。
    for _ch in range(_GB_CHANNELS):
        payload += bytes(o & 0xFF for o in song4.order)

    # インスツルメント定義（エンベロープは全て未使用＝size 0）
    payload.append(len(song4.instruments))
    for inst in song4.instruments:
        payload += _pstr(inst.name)
        payload.append(1)  # instrument mode = standard
        payload += bytes([0, 0, 0, 0])  # volume/arpeggio/duty/wave envelope size = 0
        payload += bytes([0, 0])  # sound length, selected wave（既定値）

    payload.append(0)  # ウェーブテーブル数 = 0（本実装ではカスタム波形未対応）

    for ch in range(_GB_CHANNELS):
        for pattern in song4.patterns:
            payload += _encode_pattern_channel(pattern, ch)

    compressed = zlib.compress(bytes(payload), level=9)

    with open(path, "wb") as f:
        f.write(b".DMF")
        f.write(bytes([_DMF_VERSION]))
        f.write(compressed)
