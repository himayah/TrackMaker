"""Impulse Tracker (.it) エクスポータ。

公知のITフォーマット構造（192byte固定ヘッダ + オーダーテーブル +
サンプル/パターンへの絶対オフセット・ポインタ配列 + 80byte固定サンプル
ヘッダ + パックドパターン + 生PCM）に従って構築する。

簡略化のため「インスツルメント・モード」(Flags bit2) は使用せず、
S3M/MOD と同様にサンプル番号を直接パターン内の楽器欄として扱う
オールドスタイル方式を採用している（エンベロープ機能は使わないため
機能的な差はない一方、実装の複雑さと出力サイズを大幅に削減できる）。
IT形式はパラポインタが絶対バイトオフセットで表現されるため、S3Mのような
16byteアライメント計算が不要で構造がシンプルになる。
"""

from __future__ import annotations

import random
import struct
from typing import List

from ..core.models import Pattern, Song
from . import sample_synth


def _it_note(midi_note: int) -> int:
    """MIDIノート番号を IT のノート値(0-119, C-0起点)へ変換する。"""
    return max(0, min(119, midi_note - 12))


def _encode_pattern(pattern: Pattern, num_channels: int) -> bytes:
    """1パターン分をITのパックド行フォーマットへエンコードする。

    毎回フルのマスクバイトを付与する方式（"前回と同じ"圧縮は使わない）
    を採用し、状態追跡なしで確実にデコード可能な形にしている。
    """
    body = bytearray()
    for row in range(pattern.length):
        for ch in range(num_channels):
            events = pattern.rows.get(ch, [None] * pattern.length)
            event = events[row] if row < len(events) else None
            if event is None or event.note is None:
                continue

            mask = 0
            note_byte = instrument_byte = volume_byte = None
            if event.note is not None:
                mask |= 0x01
                note_byte = 255 if event.note < 0 else _it_note(event.note)
            if event.instrument is not None:
                mask |= 0x02
                instrument_byte = event.instrument + 1
            if event.note >= 0:
                mask |= 0x04
                volume_byte = max(0, min(64, event.volume))

            body.append(((ch + 1) & 0x7F) | 0x80)  # チャンネル番号 + マスク付与フラグ
            body.append(mask)
            if mask & 0x01:
                body.append(note_byte)
            if mask & 0x02:
                body.append(instrument_byte & 0xFF)
            if mask & 0x04:
                body.append(volume_byte)
        body.append(0x00)  # 行終端
    return bytes(body)


def _build_sample_header(name: str, data_offset: int, length: int,
                          volume: int, loop: bool, c5speed: int = 8363) -> bytes:
    header = bytearray()
    header += b"IMPS"
    header += b"\x00" * 12  # DOS filename
    header.append(0)  # reserved
    header.append(min(64, volume))  # global volume
    flags = 0x01  # bit0: サンプルデータあり
    if loop:
        flags |= 0x10  # bit4: ループON
    header.append(flags)
    header.append(min(64, volume))  # default volume
    header += name.encode("ascii", "replace")[:26].ljust(26, b"\x00")
    header.append(0x01)  # Cvt: 符号付き8bitサンプル
    header.append(0)  # default pan（無効）
    header += struct.pack("<I", length)
    header += struct.pack("<I", 0)  # loop begin
    header += struct.pack("<I", length if loop else 0)  # loop end
    header += struct.pack("<I", c5speed)
    header += struct.pack("<I", 0)  # sustain loop begin
    header += struct.pack("<I", 0)  # sustain loop end
    header += struct.pack("<I", data_offset)
    header += bytes([0, 0, 0, 0])  # vibrato speed/depth/rate/waveform
    assert len(header) == 80
    return bytes(header)


def export_it(song: Song, path: str) -> None:
    """Song を Impulse Tracker (.it) として書き出す。"""
    num_channels = song.num_channels
    order = list(song.order)
    ordnum = len(order)
    smpnum = len(song.instruments)
    patnum = len(song.patterns)

    sample_raw: List[bytes] = [
        sample_synth.synthesize_for_instrument(inst, rng=random.Random(song.seed + i))
        for i, inst in enumerate(song.instruments)
    ]
    pattern_packed: List[bytes] = [_encode_pattern(p, num_channels) for p in song.patterns]

    header_fixed = 192
    order_table_offset = header_fixed
    smp_ptr_offset = order_table_offset + ordnum
    smp_ptr_size = smpnum * 4
    pat_ptr_offset = smp_ptr_offset + smp_ptr_size
    pat_ptr_size = patnum * 4
    data_start = pat_ptr_offset + pat_ptr_size

    cursor = data_start
    sample_header_offsets = []
    for _ in song.instruments:
        sample_header_offsets.append(cursor)
        cursor += 80

    pattern_offsets = []
    pattern_blocks = []
    for packed, pattern in zip(pattern_packed, song.patterns):
        pattern_offsets.append(cursor)
        block = struct.pack("<HH", len(packed), pattern.length) + b"\x00\x00\x00\x00" + packed
        pattern_blocks.append(block)
        cursor += len(block)

    sample_data_offsets = []
    for raw in sample_raw:
        sample_data_offsets.append(cursor)
        cursor += len(raw)

    # --- ヘッダ ---
    header = bytearray()
    header += b"IMPM"
    header += song.title.encode("ascii", "replace")[:26].ljust(26, b"\x00")
    header += struct.pack("<H", 0x1004)  # PHiligt（表示用、再生には無関係）
    header += struct.pack("<H", ordnum)
    header += struct.pack("<H", 0)  # InsNum（インスツルメント・モード不使用）
    header += struct.pack("<H", smpnum)
    header += struct.pack("<H", patnum)
    header += struct.pack("<H", 0x0214)  # Cwt/v
    header += struct.pack("<H", 0x0200)  # Cmwt
    header += struct.pack("<H", 0x01 | 0x08)  # Flags: stereo + linear slides
    header += struct.pack("<H", 0)  # Special
    header.append(128)  # global volume
    header.append(48)  # mix volume
    header.append(song.speed)  # initial speed
    header.append(max(31, min(255, song.bpm)))  # initial tempo
    header.append(128)  # panning separation
    header.append(0)  # pitch wheel depth
    header += struct.pack("<H", 0)  # message length
    header += struct.pack("<I", 0)  # message offset
    header += b"\x00" * 4  # reserved

    channel_pan = bytearray()
    channel_vol = bytearray()
    for ch in range(64):
        if ch < num_channels:
            channel_pan.append(32)  # 中央パン
            channel_vol.append(64)
        else:
            channel_pan.append(0xA0)  # ミュート + 中央
            channel_vol.append(64)
    header += bytes(channel_pan)
    header += bytes(channel_vol)
    assert len(header) == header_fixed

    order_table = bytes(o & 0xFF for o in order)
    smp_ptr_table = b"".join(struct.pack("<I", off) for off in sample_header_offsets)
    pat_ptr_table = b"".join(struct.pack("<I", off) for off in pattern_offsets)

    sample_headers = bytearray()
    for inst, off, raw in zip(song.instruments, sample_data_offsets, sample_raw):
        loop = not inst.is_drum
        sample_headers += _build_sample_header(
            inst.name, off, len(raw), inst.default_volume, loop)

    file_bytes = (
        bytes(header) + order_table + smp_ptr_table + pat_ptr_table
        + bytes(sample_headers) + b"".join(pattern_blocks) + b"".join(sample_raw)
    )

    with open(path, "wb") as f:
        f.write(file_bytes)
