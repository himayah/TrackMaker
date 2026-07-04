"""作曲エンジン本体: 各パートの生成モジュールを束ねて Song を組み立てる。

内部チャンネル配置（常に8chで抽象化し、出力形式ごとの実チャンネル数への
リダクションは export 側の remix ユーティリティが担当する）:

    0: melody（旋律）
    1: bass（ベース）
    2: chord_a / drone_root（和音1音目 or ドローン根音）
    3: chord_b / drone_fifth（和音2音目 or ドローン5度）
    4: chord_c（和音3音目、非和声文化圏では未使用）
    5: kick（バスドラム）
    6: snare（スネア）
    7: hihat（ハイハット）
"""

from __future__ import annotations

import random
from typing import Any, Dict, List, Optional

from ..core.models import Channel, Effect, EffectType, Instrument, NoteEvent, Pattern, Song
from ..core.scale import Scale, get_scale_by_name, random_scale
from . import bassline, drums, harmony, melody

# 文化圏ごとの General MIDI プログラム番号（MIDI出力時の音色選択に使用）。
# トラッカー出力では waveform（合成波形）を用いるため、ここは MIDI 専用の装飾。
_CULTURE_GM_PROGRAMS: Dict[str, Dict[str, int]] = {
    "西洋": {"melody": 0, "bass": 32, "chord": 48},     # Piano / Acoustic Bass / Strings
    "中東": {"melody": 73, "bass": 32, "chord": 21},    # Flute / Bass / Accordion
    "インド": {"melody": 104, "bass": 32, "chord": 109},  # Sitar / Bass / Bagpipe
    "日本": {"melody": 107, "bass": 32, "chord": 46},    # Koto / Bass / Harp
    "中国": {"melody": 110, "bass": 32, "chord": 108},   # Fiddle / Bass / Kalimba
    "ガムラン": {"melody": 114, "bass": 32, "chord": 114},  # Steel Drums
    "その他": {"melody": 0, "bass": 32, "chord": 48},
}


def _build_instruments(scale: Scale) -> List[Instrument]:
    programs = _CULTURE_GM_PROGRAMS.get(scale.culture, _CULTURE_GM_PROGRAMS["その他"])
    return [
        Instrument(0, "Melody", "melody", waveform="square",
                   gm_program=programs["melody"], default_volume=48),
        Instrument(1, "Bass", "bass", waveform="triangle",
                   gm_program=programs["bass"], default_volume=52),
        Instrument(2, "Chord/Drone", "chord", waveform="sine",
                   gm_program=programs["chord"], default_volume=36),
        Instrument(3, "Kick", "drum_kick", waveform="sine",
                   gm_program=0, is_drum=True, default_volume=60),
        Instrument(4, "Snare", "drum_snare", waveform="noise",
                   gm_program=0, is_drum=True, default_volume=50),
        Instrument(5, "Hihat", "drum_hihat", waveform="noise",
                   gm_program=0, is_drum=True, default_volume=40),
    ]


def _build_channels() -> List[Channel]:
    names = ["Melody", "Bass", "Chord A", "Chord B", "Chord C", "Kick", "Snare", "Hihat"]
    default_instruments = [0, 1, 2, 2, 2, 3, 4, 5]
    is_drum = [False, False, False, False, False, True, True, True]
    return [
        Channel(i, names[i], default_instrument=default_instruments[i],
                is_drum_channel=is_drum[i])
        for i in range(8)
    ]


def _build_pattern(pattern_id: int, scale: Scale, rng: random.Random,
                    config: Dict[str, Any]) -> Pattern:
    rows = config["rows_per_pattern"]
    pattern = Pattern(id=pattern_id, length=rows)

    start_degree = rng.choice([0, 0, 2, 4])  # トニック始まりを優先しつつ変化をつける
    melody_grid = melody.generate_melody_line(scale, rng, rows, start_degree=start_degree)
    harmony_grid = harmony.generate_harmony_track(
        scale, rng, rows, change_rows=config["chord_change_rows"])
    bass_grid = bassline.generate_bassline(
        scale, rng, rows, harmony_grid, pulse_rows=config["bass_pulse_rows"])
    drum_grids = drums.generate_drum_grid(rng, rows)

    for row in range(rows):
        if melody_grid[row] is not None:
            pattern.set_event(0, row, NoteEvent(
                note=melody_grid[row], instrument=0, volume=50))

        if bass_grid[row] is not None:
            pattern.set_event(1, row, NoteEvent(
                note=bass_grid[row], instrument=1, volume=54))

        chord_notes = harmony_grid[row]
        if chord_notes is not None:
            for slot, pitch in enumerate(chord_notes[:3]):
                pattern.set_event(2 + slot, row, NoteEvent(
                    note=pitch, instrument=2, volume=34))

        if drum_grids["kick"][row]:
            pattern.set_event(5, row, NoteEvent(note=36, instrument=3, volume=60))
        if drum_grids["snare"][row]:
            pattern.set_event(6, row, NoteEvent(note=38, instrument=4, volume=50))
        if drum_grids["hihat"][row]:
            pattern.set_event(7, row, NoteEvent(note=42, instrument=5, volume=36))

    # パターン末尾にスピード/テンポ変更以外の後始末は不要。空チャンネルも
    # ensure_channel で埋めておき、後段のエクスポータが安全に走査できるようにする。
    for ch in range(8):
        pattern.ensure_channel(ch)
    return pattern


def _build_arrangement(num_patterns: int, rng: random.Random) -> List[int]:
    """パターン再生順（order table）を組み立てる。

    3パターン以上ある場合は A-B-A-C のような反復構造を持たせ、
    単純な羅列より音楽的なまとまりを出す。
    """
    if num_patterns <= 2:
        return list(range(num_patterns)) * 2
    order = [0, 1, 0]
    for p in range(2, num_patterns):
        order.append(p)
    order.append(0)
    return order


def generate_song(seed: Optional[int] = None, title: Optional[str] = None,
                   scale_name: Optional[str] = None,
                   config: Optional[Dict[str, Any]] = None) -> Song:
    """乱数シードから曲全体（Song）を生成する。

    Args:
        seed: 乱数シード。None ならランダムに決定される。
        title: 曲タイトル。None なら自動生成。
        scale_name: 音階名を強制指定したい場合に指定（部分一致）。
            None ならライブラリからランダムに選ばれる。
        config: config.load_config() が返す設定辞書。None ならデフォルト値。
    """
    from ..config import DEFAULT_CONFIG
    cfg = config or dict(DEFAULT_CONFIG)

    if seed is None:
        seed = random.randrange(0, 2**31 - 1)
    rng = random.Random(seed)

    scale = get_scale_by_name(scale_name) if scale_name else random_scale(rng)
    scale.root = rng.randint(cfg["root_note_min"], cfg["root_note_max"])

    bpm = rng.randint(cfg["bpm_min"], cfg["bpm_max"])
    auto_title = f"{scale.name} ({scale.culture}) Random Composition"

    song = Song(
        title=title or auto_title,
        seed=seed,
        bpm=bpm,
        speed=cfg["speed"],
        scale=scale,
        channels=_build_channels(),
        instruments=_build_instruments(scale),
        rows_per_pattern=cfg["rows_per_pattern"],
    )

    for i in range(cfg["num_patterns"]):
        song.patterns.append(_build_pattern(i, scale, rng, cfg))

    song.order = _build_arrangement(cfg["num_patterns"], rng)
    return song
