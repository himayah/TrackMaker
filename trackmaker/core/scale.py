"""Scale（音階）モデルと、世界各地の音階ライブラリ。

Scale は西洋音楽の教会旋法だけでなく、中東マカーム・インドのラーガ・
日本の伝統音階・中国五声・ガムラン音階など、世界中の音階を同一の
抽象構造（root と intervals）で表現する。

intervals は「音階を構成する隣接音間の半音ステップ数の配列」であり、
1オクターブ内で合計 12 になる（例: メジャースケール = [2,2,1,2,2,2,1]）。
この設計により、音階の文化的出自にかかわらず同じアルゴリズムで
音高列を生成できる。

なお、マカームやラーガの一部は本来 12平均律に収まらない微分音
（四分音など）を含むが、本エンジンは12平均律トラッカー/MIDIへの
出力を前提とするため、最も近い12平均律の近似値で表現している。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class Scale:
    """音階の抽象モデル。

    Attributes:
        name: 音階名。
        culture: 文化圏タグ（表示・分類用）。
        intervals: 隣接スケール度数間の半音ステップ配列。合計12。
        harmonic: True なら和音進行を用いる文化圏、False なら
            ドローン＋旋律構造を用いる文化圏として扱う。
        root: 基音（MIDIノート番号）。Scale インスタンス生成時に
            作曲エンジンが具体的な root を割り当てる。
    """

    name: str
    culture: str
    intervals: List[int]
    harmonic: bool
    root: int = 60  # 既定は MIDI C4

    def degree_offsets(self) -> List[int]:
        """root からの半音オフセット配列（0始まり、オクターブ内）を返す。"""
        offsets = [0]
        acc = 0
        # 最後のステップはオクターブに戻るためのものなので度数には含めない
        for step in self.intervals[:-1]:
            acc += step
            offsets.append(acc)
        return offsets

    @property
    def num_degrees(self) -> int:
        return len(self.intervals)

    def pitch_for_degree(self, degree: int, octave_shift: int = 0) -> int:
        """スケール度数（0始まり、負数や num_degrees 超もオクターブ折返しで解釈）から
        MIDI ノート番号を求める。

        Args:
            degree: スケール上の度数。0 = root。 負数・大きい数はオクターブを跨ぐ。
            octave_shift: 追加でシフトするオクターブ数。
        """
        offsets = self.degree_offsets()
        n = len(offsets)
        octave, idx = divmod(degree, n)
        pitch = self.root + offsets[idx] + 12 * (octave + octave_shift)
        return pitch

    def clamp_to_range(self, midi_note: int, low: int = 0, high: int = 127) -> int:
        """MIDI ノート番号をオクターブ単位で [low, high] に収める。"""
        while midi_note < low:
            midi_note += 12
        while midi_note > high:
            midi_note -= 12
        return midi_note


def _scale(name: str, culture: str, intervals: List[int], harmonic: bool) -> Scale:
    assert sum(intervals) == 12, f"{name}: intervals must sum to 12 (got {sum(intervals)})"
    return Scale(name=name, culture=culture, intervals=intervals, harmonic=harmonic)


# ============================================================
# 世界の音階ライブラリ
# ============================================================
# harmonic=True  : 和声文化圏 → コード進行を使用
# harmonic=False : 非和声文化圏 → ドローン＋旋律構造を使用
SCALE_LIBRARY: List[Scale] = [
    # ---- 2.1 西洋音楽 ----
    _scale("Major", "西洋", [2, 2, 1, 2, 2, 2, 1], True),
    _scale("Natural Minor", "西洋", [2, 1, 2, 2, 1, 2, 2], True),
    _scale("Harmonic Minor", "西洋", [2, 1, 2, 2, 1, 3, 1], True),
    _scale("Melodic Minor", "西洋", [2, 1, 2, 2, 2, 2, 1], True),
    _scale("Dorian", "西洋", [2, 1, 2, 2, 2, 1, 2], True),
    _scale("Phrygian", "西洋", [1, 2, 2, 2, 1, 2, 2], True),
    _scale("Lydian", "西洋", [2, 2, 2, 1, 2, 2, 1], True),
    _scale("Mixolydian", "西洋", [2, 2, 1, 2, 2, 1, 2], True),
    _scale("Locrian", "西洋", [1, 2, 2, 1, 2, 2, 2], True),

    # ---- 2.2 中東・アラブ音楽（マカーム、12平均律近似） ----
    _scale("Hijaz", "中東", [1, 3, 1, 2, 1, 2, 2], True),
    _scale("Rast", "中東", [2, 2, 1, 2, 2, 1, 2], True),
    _scale("Bayati", "中東", [1, 2, 2, 2, 1, 2, 2], True),
    _scale("Kurd", "中東", [1, 2, 2, 2, 1, 2, 2], True),
    _scale("Saba", "中東", [1, 2, 1, 2, 2, 2, 2], True),
    _scale("Nahawand", "中東", [2, 1, 2, 2, 1, 3, 1], True),

    # ---- 2.3 インド音楽（ラーガ、上行形を簡略化） ----
    _scale("Raga Bhairav", "インド", [1, 3, 1, 2, 1, 3, 1], False),
    _scale("Raga Yaman", "インド", [2, 2, 2, 1, 2, 2, 1], False),
    _scale("Raga Todi", "インド", [1, 2, 3, 1, 1, 3, 1], False),
    _scale("Raga Kafi", "インド", [2, 1, 2, 2, 2, 1, 2], False),
    _scale("Raga Marwa", "インド", [1, 3, 2, 1, 2, 2, 1], False),
    _scale("Raga Kalyan", "インド", [2, 2, 2, 1, 2, 1, 2], False),

    # ---- 2.4 日本の音階（多くは5音音階） ----
    _scale("In Scale (陰音階)", "日本", [1, 4, 2, 1, 4], False),
    _scale("Yo Scale (陽音階)", "日本", [2, 3, 2, 2, 3], False),
    _scale("Ryukyu Scale (琉球音階)", "日本", [4, 1, 2, 4, 1], False),
    _scale("Miyako-bushi (都節音階)", "日本", [1, 4, 2, 1, 4], False),
    _scale("Minyo Scale (民謡音階)", "日本", [3, 2, 2, 3, 2], False),

    # ---- 2.5 中国・東アジア（五声、メジャーペンタトニックの各モード） ----
    _scale("Gong (宮)", "中国", [2, 2, 3, 2, 3], False),
    _scale("Shang (商)", "中国", [2, 3, 2, 3, 2], False),
    _scale("Jue (角)", "中国", [3, 2, 3, 2, 2], False),
    _scale("Zhi (徴)", "中国", [2, 3, 2, 2, 3], False),
    _scale("Yu (羽)", "中国", [3, 2, 2, 3, 2], False),

    # ---- 2.6 東南アジア（ガムラン、12平均律近似） ----
    _scale("Pelog", "ガムラン", [1, 2, 4, 1, 4], False),
    _scale("Slendro", "ガムラン", [2, 3, 2, 2, 3], False),

    # ---- 2.7 その他の民族音階 ----
    _scale("Whole Tone", "その他", [2, 2, 2, 2, 2, 2], True),
    _scale("Octatonic", "その他", [2, 1, 2, 1, 2, 1, 2, 1], True),
    _scale("Hungarian Minor", "その他", [2, 1, 3, 1, 1, 3, 1], True),
    _scale("Arabic Scale", "その他", [1, 3, 1, 2, 1, 3, 1], True),
    _scale("Persian Scale", "その他", [1, 3, 1, 1, 2, 3, 1], True),
    _scale("Blues Scale", "その他", [3, 2, 1, 1, 3, 2], True),
    _scale("Bebop Major", "その他", [2, 2, 1, 2, 1, 1, 2, 1], True),
    _scale("Bebop Dominant", "その他", [2, 2, 1, 2, 2, 1, 1, 1], True),
]


def get_scale_by_name(name: str) -> Scale:
    """名前（部分一致・大文字小文字無視）で音階を検索する。"""
    lname = name.lower()
    for s in SCALE_LIBRARY:
        if s.name.lower() == lname or lname in s.name.lower():
            # コピーを返し、呼び出し側の root 変更が原本に影響しないようにする
            return Scale(name=s.name, culture=s.culture, intervals=list(s.intervals),
                         harmonic=s.harmonic, root=s.root)
    raise KeyError(f"scale '{name}' not found in library")


def random_scale(rng) -> Scale:
    """乱数生成器 rng（random.Random）を使ってライブラリからランダムに1つ選ぶ。"""
    template = rng.choice(SCALE_LIBRARY)
    return Scale(name=template.name, culture=template.culture,
                 intervals=list(template.intervals), harmonic=template.harmonic,
                 root=template.root)


def list_scale_names() -> List[str]:
    return [f"{s.name} [{s.culture}]" for s in SCALE_LIBRARY]
