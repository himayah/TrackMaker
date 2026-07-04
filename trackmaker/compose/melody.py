"""メロディ生成: モチーフ生成とその変形（反行・逆行・拡大・縮小）。

メロディは「スケール度数（root=0とした相対度数）」の列として抽象的に
組み立て、最後に Scale.pitch_for_degree() で具体的な MIDI ノート番号へ
変換する。度数ベースで扱うことで、どんな音階（西洋・非西洋問わず）でも
同じアルゴリズムが使える。
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import List, Optional, Tuple

from ..core.scale import Scale


@dataclass
class Motif:
    """短い旋律の断片。

    Attributes:
        steps: 直前の音からの相対スケール度数移動量のリスト
            （最初の音は0からの相対、つまり steps[0] は開始度数からの移動）。
        durations: 各音の長さ（行数単位）。
    """

    steps: List[int]
    durations: List[int]

    def copy(self) -> "Motif":
        return Motif(list(self.steps), list(self.durations))


def generate_motif(rng: random.Random, note_count: int = 4, max_leap: int = 3,
                    duration_choices: Tuple[int, ...] = (1, 2, 4)) -> Motif:
    """跳躍幅を max_leap 度数以内に制御したランダムなモチーフを生成する。"""
    steps = [rng.randint(-max_leap, max_leap) for _ in range(note_count)]
    # 全て0（同音連打）は単調すぎるので最低1音は動かす
    if all(s == 0 for s in steps):
        steps[0] = rng.choice([-2, -1, 1, 2])
    durations = [rng.choice(duration_choices) for _ in range(note_count)]
    return Motif(steps, durations)


def invert(motif: Motif) -> Motif:
    """反行形（各移動量の符号を反転）。"""
    return Motif([-s for s in motif.steps], list(motif.durations))


def retrograde(motif: Motif) -> Motif:
    """逆行形（音の並びを逆順に）。"""
    return Motif(list(reversed(motif.steps)), list(reversed(motif.durations)))


def augment(motif: Motif, factor: int = 2) -> Motif:
    """拡大形（音価をfactor倍に引き伸ばす）。"""
    return Motif(list(motif.steps), [d * factor for d in motif.durations])


def diminish(motif: Motif, factor: int = 2) -> Motif:
    """縮小形（音価を1/factorに切り詰める、最小1行）。"""
    return Motif(list(motif.steps), [max(1, d // factor) for d in motif.durations])


def realize_motif(scale: Scale, motif: Motif, start_degree: int,
                   octave_shift: int = 0) -> List[Tuple[int, int]]:
    """モチーフを (MIDIノート番号, 音価) のリストへ具体化する。

    Returns:
        [(pitch, duration_rows), ...] のリスト。
    """
    result: List[Tuple[int, int]] = []
    degree = start_degree
    for step, dur in zip(motif.steps, motif.durations):
        degree += step
        pitch = scale.pitch_for_degree(degree, octave_shift)
        pitch = scale.clamp_to_range(pitch, low=36, high=96)
        result.append((pitch, dur))
    return result


def generate_melody_line(scale: Scale, rng: random.Random, total_rows: int,
                          start_degree: int = 0,
                          octave_shift: int = 0) -> List[Optional[int]]:
    """パターン全体を埋めるメロディの行グリッドを生成する。

    モチーフを1つ生成し、原形・反行・逆行・拡大・縮小をランダムに
    組み合わせて総行数を埋めることで、統一感と変化を両立させる。

    Returns:
        長さ total_rows のリスト。ノートが鳴る行には MIDI ノート番号、
        それ以外は None。
    """
    grid: List[Optional[int]] = [None] * total_rows
    base_motif = generate_motif(rng, note_count=rng.randint(3, 6))

    variations = [base_motif, invert(base_motif), retrograde(base_motif)]
    variations.append(augment(base_motif, 2))
    variations.append(diminish(base_motif, 2))

    degree = start_degree
    row = 0
    while row < total_rows:
        motif = rng.choice(variations).copy()
        notes = realize_motif(scale, motif, degree, octave_shift)
        for pitch, dur in notes:
            if row >= total_rows:
                break
            grid[row] = pitch
            row += dur
        # 次のフレーズはトニックへ引き戻す確率を持たせ、調性感を維持する
        degree = 0 if rng.random() < 0.35 else degree + rng.randint(-2, 2)
    return grid
