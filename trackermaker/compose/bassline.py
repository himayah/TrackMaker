"""ベースライン生成。

和声文化圏ではコードのルート音を中心に、経過音を交えたベースラインを
生成する。非和声文化圏ではスケールの root を中心としたドローン的な
ベース（同じ音を規則的に打ち直すペダルポイント）を生成する。
"""

from __future__ import annotations

import random
from typing import List, Optional

from ..core.scale import Scale


def generate_bassline(scale: Scale, rng: random.Random, total_rows: int,
                       harmony_grid: List[Optional[List[int]]],
                       pulse_rows: int = 4) -> List[Optional[int]]:
    """パターン全体のベース・グリッドを生成する。

    Args:
        harmony_grid: harmony.generate_harmony_track() の出力。
            和音/ドローンの根音をベースの中心音として利用する。
        pulse_rows: ベース音を打ち直す間隔（行数）。
    """
    grid: List[Optional[int]] = [None] * total_rows

    # 現在有効な根音（harmony_gridの直近のエントリを追跡）
    current_root = scale.clamp_to_range(scale.root - 12, 24, 60)

    for row in range(total_rows):
        if harmony_grid[row] is not None:
            current_root = scale.clamp_to_range(harmony_grid[row][0] - 12, 24, 60)

        if row % pulse_rows != 0:
            continue

        if scale.harmonic:
            # 和声文化圏: ルート中心 + まれに経過音（1度上下）でウォーキング感を出す
            if rng.random() < 0.75:
                grid[row] = current_root
            else:
                offsets = scale.degree_offsets()
                passing = rng.choice(offsets)
                grid[row] = scale.clamp_to_range(
                    scale.root - 12 + passing, 24, 60)
        else:
            # 非和声文化圏: root を中心としたドローン的ペダルトーン。
            # 単調になりすぎないよう、たまに1オクターブ上で鳴らす。
            if rng.random() < 0.15:
                grid[row] = scale.clamp_to_range(current_root + 12, 24, 72)
            else:
                grid[row] = current_root

    return grid
