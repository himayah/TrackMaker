"""ドラムパターン生成（スケールに依存しない従来のランダム生成ルール）。

16ステップ（16分音符グリッド）を基本単位とし、キック／スネア／ハイハット
それぞれに典型的なリズム型からの確率的なゆらぎを与えて生成する。
文化圏によらず一律のロジックを用いる（【4.4】仕様どおり）。
"""

from __future__ import annotations

import random
from typing import Dict, List


def generate_drum_grid(rng: random.Random, total_rows: int) -> Dict[str, List[bool]]:
    """長さ total_rows のドラムグリッドを生成する。

    Returns:
        {"kick": [...], "snare": [...], "hihat": [...]} の各値は
        長さ total_rows の bool リスト（True = そのステップで打鍵）。
    """
    kick = [False] * total_rows
    snare = [False] * total_rows
    hihat = [False] * total_rows

    for row in range(total_rows):
        step16 = row % 16

        # キック: 典型的な四つ打ちの土台（0,4,8,12）に加え、
        # シンコペーションとしてまれに追加のキックを挿入する。
        if step16 in (0, 8):
            kick[row] = rng.random() < 0.95
        elif step16 in (4, 12):
            kick[row] = rng.random() < 0.35
        else:
            kick[row] = rng.random() < 0.05

        # スネア: バックビート（4,12）を基本に、ゴーストノートをまばらに追加。
        if step16 in (4, 12):
            snare[row] = rng.random() < 0.9
        else:
            snare[row] = rng.random() < 0.06

        # ハイハット: 8分or16分刻みで敷き詰め、たまに抜く。
        if step16 % 2 == 0:
            hihat[row] = rng.random() < 0.85
        else:
            hihat[row] = rng.random() < 0.55

    return {"kick": kick, "snare": snare, "hihat": hihat}
