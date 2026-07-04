"""FastTracker 2 Extended Module (.xm) エクスポータ。

公知のXMフォーマット構造（60byte固定ヘッダ + header_size + オーダー
テーブル256byte + パターン群 + インスツルメント群）に従って構築する。

インスツルメントのボリューム/パンニング・エンベロープは全て無効化
（Type=0）した上でフィールド自体は仕様どおりのバイト数だけ確保して
いる。エンベロープが無効な場合、実プレイヤーはその内容を解釈しない
ため、細部のバイト意味づけよりも「サイズの整合性」を優先している。

サンプルデータは XM 仕様どおり差分（デルタ）エンコードした符号付き
8bit PCM として書き出す。
"""

from __future__ import annotations

import random
import struct
from typing import List

from ..core.models import Pattern, Song
from . import sample_synth

_ID_TEXT = b"Extended Module: "
_SAMPLE_HEADER_SIZE = 40
_INSTRUMENT_HEADER_SIZE = 243  # 本エクスポータが実際に書き出すバイト数と一致させる


def _xm_note(midi_note: int) -> int:
    """MIDIノート番号を XM のノート値(1-96)へ変換する（内部専用の相対マッピング）。"""
    return max(1, min(96, midi_note - 12))


def _delta_encode_8bit(raw: bytes) -> bytes:
    """XM仕様の8bitサンプル差分エンコーディング。"""
    out = bytearray(len(raw))
    prev = 0
    for i, b in enumerate(raw):
        cur = b - 256 if b >= 128 else b
        delta = (cur - prev) & 0xFF
        out[i] = delta
        prev = cur
    return bytes(out)


def _pack_pattern(pattern: Pattern, num_channels: int) -> bytes:
    body = bytearray()
    for row in range(pattern.length):
        for ch in range(num_channels):
            events = pattern.rows.get(ch, [None] * pattern.length)
            event = events[row] if row < len(events) else None

            if event is None or event.note is None:
                body.append(0x80)  # 完全な空セル
                continue

            if event.note < 0:
                body.append(0x80 | 0x01)  # ノートオフのみ
                body.append(97)
                continue

            note_val = _xm_note(event.note)
            instrument_val = (event.instrument + 1) if event.instrument is not None else 1
            volume_byte = 0x10 + max(0, min(64, event.volume))

            body.append(0x80 | 0x07)  # note + instrument + volume が続く
            body.append(note_val)
            body.append(instrument_val & 0xFF)
            body.append(volume_byte)
    return bytes(body)


def _build_instrument_block(instrument, sample_data: bytes) -> bytes:
    """1インスツルメント分（拡張ヘッダ＋サンプルヘッダ×1）を構築する。"""
    header = bytearray()
    header += struct.pack("<I", _INSTRUMENT_HEADER_SIZE)
    header += instrument.name.encode("ascii", "replace")[:22].ljust(22, b"\x00")
    header.append(0)  # instrument type
    header += struct.pack("<H", 1)  # サンプル数 = 1
    header += struct.pack("<I", _SAMPLE_HEADER_SIZE)  # サンプルヘッダ1件のサイズ
    header += bytes(96)  # サンプル・キーマップ（全音域をサンプル0に割当）
    header += bytes(48)  # ボリューム・エンベロープ点群（未使用）
    header += bytes(48)  # パンニング・エンベロープ点群（未使用）
    header += bytes([0, 0])  # ボリューム/パンニング点の数 = 0
    header += bytes([0, 0, 0])  # ボリューム: sustain/loopstart/loopend
    header += bytes([0, 0, 0])  # パンニング: sustain/loopstart/loopend
    header += bytes([0, 0])  # VolumeType, PanningType（共にエンベロープ無効）
    header += bytes([0, 0, 0, 0])  # Vibrato: type, sweep, depth, rate
    header += struct.pack("<H", 0)  # Volume fadeout
    header += bytes(2)  # reserved
    assert len(header) == _INSTRUMENT_HEADER_SIZE

    loop = not instrument.is_drum
    sample_type = 0x01 if loop else 0x00  # bit0-1: 0=no loop, 1=forward loop
    sample_header = bytearray()
    sample_header += struct.pack("<I", len(sample_data))
    sample_header += struct.pack("<I", 0)  # loop start
    sample_header += struct.pack("<I", len(sample_data) if loop else 0)  # loop length
    sample_header.append(max(0, min(64, instrument.default_volume)))
    sample_header.append(0)  # finetune
    sample_header.append(sample_type)
    sample_header.append(128)  # panning = center
    sample_header.append(0)  # relative note
    sample_header.append(0)  # reserved
    sample_header += instrument.name.encode("ascii", "replace")[:22].ljust(22, b"\x00")
    assert len(sample_header) == _SAMPLE_HEADER_SIZE

    return bytes(header) + bytes(sample_header) + _delta_encode_8bit(sample_data)


def export_xm(song: Song, path: str) -> None:
    """Song を FastTracker 2 XM (.xm) として書き出す。"""
    num_channels = song.num_channels

    file_bytes = bytearray()
    file_bytes += _ID_TEXT
    file_bytes += song.title.encode("ascii", "replace")[:20].ljust(20, b" ")
    file_bytes.append(0x1A)
    file_bytes += b"TrackerMaker".ljust(20, b" ")
    file_bytes += struct.pack("<H", 0x0104)

    header_size = 4 + 16 + 256
    file_bytes += struct.pack("<I", header_size)

    order = list(song.order)
    song_length = len(order)
    num_patterns = len(song.patterns)

    file_bytes += struct.pack("<H", song_length)
    file_bytes += struct.pack("<H", 0)  # restart position
    file_bytes += struct.pack("<H", num_channels)
    file_bytes += struct.pack("<H", num_patterns)
    file_bytes += struct.pack("<H", len(song.instruments))
    file_bytes += struct.pack("<H", 1)  # flags: bit0=1 (リニア周波数テーブル)
    file_bytes += struct.pack("<H", song.speed)  # default tempo (行あたりtick数)
    file_bytes += struct.pack("<H", song.bpm)  # default BPM

    order_table = bytes(order[:256]) + bytes(256 - min(256, len(order)))
    file_bytes += order_table

    for pattern in song.patterns:
        packed = _pack_pattern(pattern, num_channels)
        file_bytes += struct.pack("<I", 9)  # pattern header length
        file_bytes.append(0)  # packing type
        file_bytes += struct.pack("<H", pattern.length)
        file_bytes += struct.pack("<H", len(packed))
        file_bytes += packed

    for i, inst in enumerate(song.instruments):
        raw = sample_synth.synthesize_for_instrument(inst, rng=random.Random(song.seed + i))
        file_bytes += _build_instrument_block(inst, raw)

    with open(path, "wb") as f:
        f.write(bytes(file_bytes))
