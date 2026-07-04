"""MIDI (Standard MIDI File, フォーマット1) エクスポータ。

依存ライブラリなし（Python標準ライブラリの struct のみ）で SMF を
直接組み立てる。各行(row)を16分音符1つとして解釈し、テンポは
Song.bpm をそのまま四分音符の BPM として使用する。

MIDIチャンネル割り当て:
    0: melody
    1: bass
    2: chord/drone（内部チャンネル2,3,4を統合。和音は同一チャンネル上の
       複数ノートとして自然に表現できる）
    9: drums（GMパーカッションチャンネル。kick=36, snare=38, hihat=42 は
       General MIDI ドラムマップにそのまま合致する）
"""

from __future__ import annotations

import struct
from typing import List, Tuple

from ..core.models import Song

PPQN = 96
TICKS_PER_ROW = PPQN // 4  # 1行 = 16分音符


def _vlq(value: int) -> bytes:
    """MIDI可変長数値（Variable Length Quantity）にエンコードする。"""
    buf = [value & 0x7F]
    value >>= 7
    while value:
        buf.append((value & 0x7F) | 0x80)
        value >>= 7
    return bytes(reversed(buf))


def _collect_channel_events(song: Song, channel_index: int,
                             fixed_duration_ticks: int = None
                             ) -> List[Tuple[int, int, int]]:
    """指定チャンネルの (note_on_tick, note_off_tick, pitch, velocity) を集める。

    fixed_duration_ticks が None の場合はレガート
    （次のオンセットまで伸ばす）、指定時はその長さで打ち切る（ドラム用）。
    """
    onsets: List[Tuple[int, int, int]] = []  # (abs_tick, pitch, velocity)
    abs_tick = 0
    for pattern_id in song.order:
        pattern = song.pattern_by_id(pattern_id)
        events = pattern.rows.get(channel_index, [None] * pattern.length)
        for row in range(pattern.length):
            ev = events[row]
            if ev is not None and ev.note is not None and ev.note >= 0:
                velocity = max(1, min(127, int(ev.volume / 64 * 127)))
                onsets.append((abs_tick + row * TICKS_PER_ROW, ev.note, velocity))
        abs_tick += pattern.length * TICKS_PER_ROW

    total_ticks = abs_tick
    result = []
    for i, (tick, pitch, velocity) in enumerate(onsets):
        if fixed_duration_ticks is not None:
            off_tick = tick + fixed_duration_ticks
        elif i + 1 < len(onsets):
            off_tick = onsets[i + 1][0]
        else:
            off_tick = total_ticks
        off_tick = max(off_tick, tick + 1)
        result.append((tick, off_tick, pitch, velocity))
    return result


def _build_track(events_by_channel: List[List[Tuple[int, int, int, int]]],
                  midi_channel: int, program: int) -> bytes:
    """複数の内部チャンネル分のノートイベントを1つのMIDIトラックへまとめる。"""
    raw: List[Tuple[int, int, bytes]] = []  # (abs_tick, priority, bytes) priority: offを先に
    raw.append((0, 0, bytes([0xC0 | midi_channel, program & 0x7F])))

    for events in events_by_channel:
        for on_tick, off_tick, pitch, velocity in events:
            raw.append((on_tick, 1, bytes([0x90 | midi_channel, pitch & 0x7F, velocity])))
            raw.append((off_tick, 0, bytes([0x80 | midi_channel, pitch & 0x7F, 0])))

    raw.sort(key=lambda t: (t[0], t[1]))

    body = bytearray()
    prev_tick = 0
    for tick, _priority, data in raw:
        delta = max(0, tick - prev_tick)
        body += _vlq(delta)
        body += data
        prev_tick = tick

    body += _vlq(0) + bytes([0xFF, 0x2F, 0x00])  # End of Track
    return bytes(body)


def _build_tempo_track(bpm: int) -> bytes:
    microseconds_per_quarter = round(60_000_000 / bpm)
    tempo_bytes = struct.pack(">I", microseconds_per_quarter)[1:]  # 24bit
    body = bytearray()
    body += _vlq(0) + bytes([0xFF, 0x51, 0x03]) + tempo_bytes
    body += _vlq(0) + bytes([0xFF, 0x2F, 0x00])
    return bytes(body)


def _chunk(chunk_id: bytes, data: bytes) -> bytes:
    return chunk_id + struct.pack(">I", len(data)) + data


def export_midi(song: Song, path: str) -> None:
    """Song を Standard MIDI File (フォーマット1) として書き出す。"""
    programs = [inst.gm_program for inst in song.instruments]

    melody_events = [_collect_channel_events(song, 0)]
    bass_events = [_collect_channel_events(song, 1)]
    chord_events = [_collect_channel_events(song, c) for c in (2, 3, 4)]
    drum_events = [_collect_channel_events(song, c, fixed_duration_ticks=TICKS_PER_ROW // 2 or 1)
                   for c in (5, 6, 7)]

    tracks = [
        _build_tempo_track(song.bpm),
        _build_track(melody_events, midi_channel=0, program=programs[0]),
        _build_track(bass_events, midi_channel=1, program=programs[1]),
        _build_track(chord_events, midi_channel=2, program=programs[2]),
        _build_track(drum_events, midi_channel=9, program=0),
    ]

    header = struct.pack(">HHH", 1, len(tracks), PPQN)
    data = _chunk(b"MThd", header)
    for track in tracks:
        data += _chunk(b"MTrk", track)

    with open(path, "wb") as f:
        f.write(data)
