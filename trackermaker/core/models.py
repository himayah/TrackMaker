"""内部データ構造（抽象度の高い共通モデル）。

トラッカー形式（MOD/XM/IT/S3M）や MIDI など、出力形式に依存しない
抽象的な「曲」の表現を提供する。各エクスポータはこのモデルだけを
読み取って、それぞれのバイナリ形式に変換する。

設計方針:
    - Song は曲全体（テンポ、スケール、チャンネル定義、楽器、パターン、
      パターン再生順）を保持する。
    - Pattern は行(row)方向に長さ length を持つグリッドで、
      チャンネルごとに NoteEvent（または空）を格納する。
    - NoteEvent は「ノート番号（MIDI番号系, 0-127, None=無音）」
      「使用楽器」「ボリューム」「エフェクト列」を持つ。
    - Effect はコマンド名と値からなる汎用的なエフェクト表現で、
      各エクスポータがそれぞれのネイティブなエフェクトコードへ変換する。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Optional


class EffectType(Enum):
    """トラッカー系フォーマット共通の汎用エフェクト種別。

    各エクスポータは必要な分だけこの中から対応するコマンドへ変換する。
    未対応のエフェクトは無視してよい（無音動作を壊さないことを優先する）。
    """

    NONE = auto()
    ARPEGGIO = auto()          # 0xy: アルペジオ
    PORTA_UP = auto()          # 1xx: ポルタメントアップ
    PORTA_DOWN = auto()        # 2xx: ポルタメントダウン
    TONE_PORTA = auto()        # 3xx: トーンポルタメント（音程スライド）
    VIBRATO = auto()           # 4xy: ビブラート
    VOLUME_SLIDE = auto()      # Axy: ボリュームスライド
    SET_VOLUME = auto()        # Cxx: ボリューム設定
    PATTERN_BREAK = auto()     # Dxx: パターン中断
    SET_SPEED = auto()         # Fxx: スピード/テンポ設定
    NOTE_CUT = auto()          # ECx: ノートカット
    NOTE_OFF = auto()          # ノートオフ（ドローン楽器の減衰用）


@dataclass
class Effect:
    """汎用エフェクト表現。

    Attributes:
        type: エフェクト種別。
        param: エフェクトのパラメータ（0-255 の範囲で汎用的に保持）。
    """

    type: EffectType = EffectType.NONE
    param: int = 0


# ノートオフを表す特別な定数（NoteEvent.note に用いる）。
NOTE_OFF = -1


@dataclass
class NoteEvent:
    """パターン内の1マス（1チャンネル×1行）に配置されるノート情報。

    Attributes:
        note: MIDIノート番号（0-127）。None は「何も置かれていない」、
            NOTE_OFF(-1) は「鳴っている音を止める」を意味する。
        instrument: 使用する Instrument の song.instruments 内インデックス。
        volume: 0-64 のトラッカー標準レンジのボリューム。
        effects: 同時にかかる Effect のリスト（多くの形式は1つだが、
            内部モデルでは複数保持できるようにしておく）。
    """

    note: Optional[int] = None
    instrument: Optional[int] = None
    volume: int = 48
    effects: List[Effect] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return self.note is None and not self.effects


@dataclass
class Instrument:
    """楽器の抽象表現。

    MIDI 出力時は gm_program（General MIDI プログラム番号）を、
    トラッカー出力時は waveform（合成波形の種類）を用いてサンプルを
    合成する。role は作曲エンジンが「どのパートの楽器か」を判断する
    ために使うタグ。
    """

    id: int
    name: str
    role: str  # "melody" | "bass" | "chord" | "drone" | "drum_kick" 等
    waveform: str = "sine"  # "sine" | "square" | "saw" | "triangle" | "noise"
    gm_program: int = 0  # General MIDI プログラム番号 (0-127)
    is_drum: bool = False
    default_volume: int = 48  # 0-64


@dataclass
class Channel:
    """チャンネル（トラックレーン）の定義。

    NoteEvent 自体は Pattern 側にグリッドとして保持されるため、
    Channel はメタ情報（名前・既定楽器・ミュート等）のみを持つ。
    """

    index: int
    name: str
    default_instrument: Optional[int] = None
    is_drum_channel: bool = False


@dataclass
class Pattern:
    """1パターン分のノートグリッド。

    rows[channel_index] は長さ length のリストで、各要素は
    Optional[NoteEvent]（None は空マス）。
    """

    id: int
    length: int
    rows: Dict[int, List[Optional[NoteEvent]]] = field(default_factory=dict)

    def ensure_channel(self, channel_index: int) -> None:
        """指定チャンネルの行リストが未初期化なら空で作成する。"""
        if channel_index not in self.rows:
            self.rows[channel_index] = [None] * self.length

    def set_event(self, channel_index: int, row: int, event: NoteEvent) -> None:
        self.ensure_channel(channel_index)
        self.rows[channel_index][row] = event

    def get_event(self, channel_index: int, row: int) -> Optional[NoteEvent]:
        self.ensure_channel(channel_index)
        return self.rows[channel_index][row]


@dataclass
class Song:
    """曲全体を表す最上位オブジェクト。"""

    title: str
    seed: int
    bpm: int
    speed: int  # 1行あたりのティック数（トラッカー用語）
    scale: "Scale"  # 循環importを避けるため文字列注釈
    channels: List[Channel] = field(default_factory=list)
    instruments: List[Instrument] = field(default_factory=list)
    patterns: List[Pattern] = field(default_factory=list)
    order: List[int] = field(default_factory=list)  # パターン再生順（パターンindexの列）
    rows_per_pattern: int = 64

    @property
    def num_channels(self) -> int:
        return len(self.channels)

    def pattern_by_id(self, pattern_id: int) -> Pattern:
        for p in self.patterns:
            if p.id == pattern_id:
                return p
        raise KeyError(f"pattern id {pattern_id} not found")
