"""ScreamTracker 3 (.s3m) エクスポータ。

公知のS3Mフォーマット仕様（96byte固定ヘッダ + オーダーテーブル +
インスツルメント/パターンのパラポインタ配列 + 80byte固定インスツルメント
ヘッダ群 + パックドパターンデータ + 生PCMサンプル）に従って構築する。

簡略化のため:
    - パンニングテーブルは使用せず、マスターボリュームをモノラル
      設定にすることで左右偏りを回避している。
    - エフェクトコマンド列は書き出さず、ノート・インスツルメント・
      ボリュームのみを使用する（内部モデルの volume=0-64 は
      S3Mのボリュームカラムとレンジが一致するためそのまま使える）。
"""

from __future__ import annotations

import random
import struct
from typing import List, Tuple

from ..core.models import Pattern, Song
from . import sample_synth

S3M_ROWS = 64


def _note_to_s3m_bytes(note: int) -> int:
    """MIDIノート番号を S3M の (octave<<4 | note_in_octave) 形式に変換する。"""
    octave = max(0, min(9, note // 12 - 1))
    note_in_oct = note % 12
    return (octave << 4) | note_in_oct


def _encode_pattern(pattern: Pattern, num_channels: int) -> bytes:
    """1パターン分をS3Mのパックド行フォーマットへエンコードする。"""
    body = bytearray()
    for row in range(S3M_ROWS):
        for ch in range(num_channels):
            events = pattern.rows.get(ch, [None] * pattern.length)
            event = events[row] if row < len(events) else None
            if event is None or event.note is None:
                continue

            what = (ch & 0x1F) | 0x20 | 0x40  # note+instrument, volume を付与
            if event.note < 0:
                note_byte = 254  # ノートオフ
            else:
                note_byte = _note_to_s3m_bytes(event.note)
            instrument_byte = (event.instrument + 1) if event.instrument is not None else 0
            volume_byte = max(0, min(64, event.volume))

            body.append(what)
            body.append(note_byte)
            body.append(instrument_byte)
            body.append(volume_byte)
        body.append(0x00)  # 行終端マーカー
    return bytes(body)


def _build_instrument_header(name: str, memseg: int, length: int,
                              volume: int, loop: bool, c2spd: int = 8363) -> bytes:
    header = bytearray()
    header.append(1)  # type = 1 (PCM sample)
    header += b"\x00" * 12  # dosname
    header.append((memseg >> 16) & 0xFF)  # memseg 上位byte
    header += struct.pack("<H", memseg & 0xFFFF)  # memseg 下位word
    header += struct.pack("<I", length)
    loop_begin = 0
    loop_end = length if loop else 0
    header += struct.pack("<I", loop_begin)
    header += struct.pack("<I", loop_end)
    header.append(max(0, min(64, volume)))
    header.append(0)  # reserved
    header.append(0)  # packing = 0 (無圧縮)
    header.append(0x01 if loop else 0x00)  # flags: bit0 = loop on
    header += struct.pack("<I", c2spd)
    header += b"\x00" * 12
    header += name.encode("ascii", "replace")[:28].ljust(28, b"\x00")
    header += b"SCRS"
    assert len(header) == 80
    return bytes(header)


def export_s3m(song: Song, path: str) -> None:
    """Song を ScreamTracker 3 (.s3m) として書き出す。"""
    num_channels = song.num_channels
    order = list(song.order)
    if len(order) % 2 == 1:
        order.append(255)  # 慣例的にオーダー数を偶数に揃える終端マーカー
    ordnum = len(order)
    insnum = len(song.instruments)
    patnum = len(song.patterns)

    # --- 各パターンのパックドデータと各楽器のPCMサンプルを先に生成する ---
    pattern_data_list: List[bytes] = [
        _encode_pattern(p, num_channels) for p in song.patterns
    ]
    sample_data_list: List[bytes] = []
    for i, inst in enumerate(song.instruments):
        raw = sample_synth.synthesize_for_instrument(inst, rng=random.Random(song.seed + i))
        # S3Mは符号なし8bit PCMを標準とする（signed→unsignedへ+128変換）
        unsigned = bytes((b + 128) & 0xFF for b in raw)
        sample_data_list.append(unsigned)

    # --- レイアウト計算（region2 = 楽器ヘッダ + パターン + サンプルデータ）---
    prefix_size = 96 + ordnum + insnum * 2 + patnum * 2
    region2_start = (prefix_size + 15) // 16 * 16
    pad_before_region2 = region2_start - prefix_size

    local = insnum * 80
    inst_header_offsets = [region2_start + i * 80 for i in range(insnum)]

    pattern_ptrs: List[int] = []
    pattern_blocks: List[Tuple[int, bytes]] = []
    for data in pattern_data_list:
        block = struct.pack("<H", len(data)) + data
        pad = (-local) % 16
        local += pad
        pattern_ptrs.append((region2_start + local) // 16)
        pattern_blocks.append((pad, block))
        local += len(block)

    sample_memsegs: List[int] = []
    sample_blocks: List[Tuple[int, bytes]] = []
    for data in sample_data_list:
        pad = (-local) % 16
        local += pad
        sample_memsegs.append((region2_start + local) // 16)
        sample_blocks.append((pad, data))
        local += len(data)

    # --- region2 の実バイト列を構築 ---
    region2 = bytearray()
    for inst, memseg, data in zip(song.instruments, sample_memsegs, sample_data_list):
        loop = not inst.is_drum
        region2 += _build_instrument_header(
            inst.name, memseg, len(data), inst.default_volume, loop)
    for pad, block in pattern_blocks:
        region2 += b"\x00" * pad
        region2 += block
    for pad, data in sample_blocks:
        region2 += b"\x00" * pad
        region2 += data

    # --- ヘッダ本体 ---
    header = bytearray()
    header += song.title.encode("ascii", "replace")[:28].ljust(28, b"\x00")
    header.append(0x1A)
    header.append(16)  # type = 16 (ST3 module)
    header += b"\x00\x00"
    header += struct.pack("<H", ordnum)
    header += struct.pack("<H", insnum)
    header += struct.pack("<H", patnum)
    header += struct.pack("<H", 0)  # flags
    header += struct.pack("<H", 0x1320)  # cwt/v (トラッカーバージョン識別)
    header += struct.pack("<H", 2)  # ffi = 2 (unsigned samples)
    header += b"SCRM"
    header.append(64)  # global volume
    header.append(song.speed)  # initial speed
    header.append(max(32, min(255, song.bpm)))  # initial tempo
    header.append(0x30)  # master volume（モノラル、bit7=0）
    header.append(0)  # ultraclick removal
    header.append(0x00)  # default panning無効（0xFC以外＝パンテーブルなし）
    header += b"\x00" * 8
    header += struct.pack("<H", 0)  # special = なし
    channel_settings = bytearray(b"\xFF" * 32)
    for i in range(min(num_channels, 16)):
        channel_settings[i] = i  # 0-7=PCM左系だがモノラルmixなので影響小
    header += bytes(channel_settings)
    assert len(header) == 96

    order_table = bytes(order) + bytes([255] * (ordnum - len(order)))
    inst_ptr_table = b"".join(struct.pack("<H", off // 16) for off in inst_header_offsets)
    pattern_ptr_table = b"".join(struct.pack("<H", p) for p in pattern_ptrs)

    file_bytes = (
        bytes(header) + order_table + inst_ptr_table + pattern_ptr_table
        + b"\x00" * pad_before_region2 + bytes(region2)
    )

    with open(path, "wb") as f:
        f.write(file_bytes)
