"""ProTracker MOD (.mod, 4チャンネル / 31インスツルメント) エクスポータ。

フォーマットは "M.K." シグネチャの標準31サンプルMODとして出力する。
MODは常に4チャンネル・1パターン=64行固定という制約があるため、
export 前に channel_remix で内部8chを4chへ縮約し、pattern長も
64行に正規化する。

参考にした仕様（公知のMODフォーマット構造）:
    - 20byte songタイトル
    - 31個のサンプルヘッダ (各30byte: name22 + length2 + finetune1 +
      volume1 + repeat_offset2 + repeat_length2)
    - 1byte song length（オーダーテーブルの使用エントリ数）
    - 1byte 0x7F（restart, 歴史的固定値）
    - 128byte オーダーテーブル
    - 4byte シグネチャ "M.K."
    - パターンデータ（1パターン=64行×4ch×4byte）
    - 各サンプルの生PCMデータ（符号付き8bit）
"""

from __future__ import annotations

from typing import List, Optional

from ..core.models import NoteEvent, Pattern, Song
from . import sample_synth
from .channel_remix import remix_to_channels

MOD_ROWS = 64
MOD_BASE_MIDI = 24  # period table index0 が指すMIDIノート番号（内部専用の基準）

# ProTracker 標準ピリオドテーブル（finetune=0, オクターブ1-3, 36音）
_PERIOD_TABLE = [
    856, 808, 762, 720, 678, 640, 604, 570, 538, 508, 480, 453,
    428, 404, 381, 360, 340, 320, 302, 285, 269, 254, 240, 226,
    214, 202, 190, 180, 170, 160, 151, 143, 135, 127, 120, 113,
]


def _period_for_midi_note(note: int) -> int:
    """MIDIノート番号を、内部基準に基づく Amiga ピリオド値へ変換する。"""
    idx = note - MOD_BASE_MIDI
    while idx < 0:
        idx += 12
    while idx >= len(_PERIOD_TABLE):
        idx -= 12
    return _PERIOD_TABLE[idx]


def _normalize_rows(pattern: Pattern, num_channels: int) -> List[List[Optional[NoteEvent]]]:
    """パターンをMOD固定長(64行)へ正規化する（切り詰め/空行埋め）。"""
    grid: List[List[Optional[NoteEvent]]] = []
    for ch in range(num_channels):
        src = pattern.rows.get(ch, [None] * pattern.length)
        if len(src) >= MOD_ROWS:
            grid.append(src[:MOD_ROWS])
        else:
            grid.append(src + [None] * (MOD_ROWS - len(src)))
    return grid


def _encode_cell(event: Optional[NoteEvent]) -> bytes:
    """1マス分を MOD の4byteノートエンコーディングへ変換する。"""
    if event is None or event.note is None:
        return bytes([0, 0, 0, 0])

    sample_number = (event.instrument + 1) if event.instrument is not None else 0
    sample_number = max(0, min(31, sample_number))

    if event.note < 0:  # NOTE_OFF: 明示的にボリューム0で無音化する
        period = 0
        effect, param = 0xC, 0
    else:
        period = _period_for_midi_note(event.note)
        effect, param = 0xC, max(0, min(64, event.volume))  # Cxx: ボリューム設定

    byte0 = (sample_number & 0xF0) | ((period >> 8) & 0x0F)
    byte1 = period & 0xFF
    byte2 = ((sample_number & 0x0F) << 4) | (effect & 0x0F)
    byte3 = param & 0xFF
    return bytes([byte0, byte1, byte2, byte3])


def _pack_sample_header(name: str, data: bytes, volume: int, loop: bool) -> bytes:
    name_bytes = name.encode("ascii", "replace")[:22].ljust(22, b"\x00")
    length_words = len(data) // 2
    finetune = 0
    if loop:
        repeat_offset_words = 0
        repeat_length_words = max(1, length_words)
    else:
        repeat_offset_words = 0
        repeat_length_words = 1
    header = bytearray()
    header += name_bytes
    header += length_words.to_bytes(2, "big")
    header += bytes([finetune & 0x0F])
    header += bytes([max(0, min(64, volume))])
    header += repeat_offset_words.to_bytes(2, "big")
    header += repeat_length_words.to_bytes(2, "big")
    return bytes(header)


def export_mod(song: Song, path: str) -> None:
    """Song を ProTracker MOD (.mod) として書き出す。"""
    song4 = remix_to_channels(song, 4)

    data = bytearray()
    data += song4.title.encode("ascii", "replace")[:20].ljust(20, b"\x00")

    # 31サンプルスロット分のヘッダ（未使用は空データ）
    sample_bytes_list: List[bytes] = []
    rng_seed_offset = 0
    for slot in range(31):
        if slot < len(song4.instruments):
            inst = song4.instruments[slot]
            import random
            sample_data = sample_synth.synthesize_for_instrument(
                inst, rng=random.Random(song4.seed + slot))
            is_loop = not inst.is_drum
            data += _pack_sample_header(inst.name, sample_data, inst.default_volume, is_loop)
            sample_bytes_list.append(sample_data)
        else:
            data += _pack_sample_header("", b"", 0, False)
            sample_bytes_list.append(b"")

    song_length = max(1, min(128, len(song4.order)))
    data += bytes([song_length])
    data += bytes([0x7F])  # restart byte（歴史的固定値）

    order_table = list(song4.order[:128]) + [0] * (128 - min(128, len(song4.order)))
    data += bytes(order_table)

    data += b"M.K."

    for pattern in song4.patterns:
        grid = _normalize_rows(pattern, 4)
        for row in range(MOD_ROWS):
            for ch in range(4):
                data += _encode_cell(grid[ch][row])

    for sample_data in sample_bytes_list:
        data += sample_data

    with open(path, "wb") as f:
        f.write(bytes(data))
