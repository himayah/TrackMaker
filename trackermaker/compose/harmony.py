"""和声 / ドローン生成。

西洋・アラブ・ペルシャなど「和声文化圏」の音階では機能和声的な
コード進行を生成する。一方、日本・ガムラン・インドのラーガなど
「非和声文化圏」の音階では和音という概念が薄いため、持続する
ドローン（保続音）と旋律構造の組み合わせを採用する。

どちらを使うかは Scale.harmonic フラグで自動的に切り替わる
（【4.2 コード進行】の仕様どおり）。
"""

from __future__ import annotations

import random
from typing import List, Optional, Tuple

from ..core.scale import Scale

# 度数ベースのコード進行パターン（degree, degree, degree, degree の4小節分）。
# 7度音階における I-IV-V-I 等の代表的な進行を汎用度数で表現している。
_PROGRESSION_PATTERNS: List[List[int]] = [
    [0, 3, 4, 0],   # I - IV - V - I
    [0, 5, 3, 4],   # I - vi - IV - V
    [0, 4, 5, 3],   # I - V - vi - IV
    [0, 2, 3, 4],   # I - iii - IV - V
]


def chord_from_degree(scale: Scale, root_degree: int, octave_shift: int = 0) -> List[int]:
    """指定度数を根音として、1つ飛ばしに3音重ねた「三和音」を生成する。

    非西洋の5音音階などでも度数の折返し（modulo）で機能するため、
    文化圏を問わず同じロジックで和音的な響きを近似できる。
    """
    third = scale.pitch_for_degree(root_degree + 2, octave_shift)
    fifth = scale.pitch_for_degree(root_degree + 4, octave_shift)
    root = scale.pitch_for_degree(root_degree, octave_shift)
    return [scale.clamp_to_range(p, 36, 84) for p in (root, third, fifth)]


def build_chord_progression(scale: Scale, rng: random.Random) -> List[List[int]]:
    """4コード分の進行を生成する（和声文化圏用）。"""
    pattern = rng.choice(_PROGRESSION_PATTERNS)
    n = scale.num_degrees
    return [chord_from_degree(scale, degree % n) for degree in pattern]


def build_drone(scale: Scale) -> List[int]:
    """ドローン（保続音）の構成音を求める（非和声文化圏用）。

    ルートに加えて、音階内で完全5度（7半音）に最も近い度数があれば
    それも重ねる。無ければルートのオクターブ違いのみにする。
    """
    offsets = scale.degree_offsets()
    root = scale.clamp_to_range(scale.root, 36, 72)
    notes = [root]
    closest = min(offsets, key=lambda o: abs(o - 7))
    if closest != 0:
        notes.append(scale.clamp_to_range(scale.root + closest, 36, 72))
    return notes


def generate_harmony_track(scale: Scale, rng: random.Random, total_rows: int,
                            change_rows: int = 16) -> List[Optional[List[int]]]:
    """パターン全体の和声/ドローン・グリッドを生成する。

    Returns:
        長さ total_rows のリスト。和音/ドローンが鳴る行には MIDI
        ノート番号のリスト、それ以外は None。
    """
    grid: List[Optional[List[int]]] = [None] * total_rows

    if scale.harmonic:
        progression = build_chord_progression(scale, rng)
        idx = 0
        row = 0
        while row < total_rows:
            grid[row] = progression[idx % len(progression)]
            idx += 1
            row += change_rows
    else:
        drone_notes = build_drone(scale)
        # ドローンは曲頭で1度鳴らし、以後は伸ばしっぱなし（トラッカー的には
        # ロングノート＋no-op行として表現する＝ Noneのまま経過させる）。
        grid[0] = drone_notes
    return grid
