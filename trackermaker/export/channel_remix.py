"""チャンネル数の少ないフォーマット（MOD=4ch、DMF=システム依存 等）向けの
チャンネル・リダクション（合成/間引き）ユーティリティ。

内部モデルは常に8チャンネル（melody/bass/chord*3/kick/snare/hihat）の
抽象表現を保持する。出力形式のネイティブなチャンネル数がそれより少ない
場合、このモジュールでチャンネルを論理的にグルーピングし、各グループ
内で「その行に鳴っているイベントを優先順位付きで1つ選ぶ」ことで
チャンネル数を減らす。これにより内部データ構造自体は変更せず、
出力直前の変換だけで多様な出力チャンネル数に対応できる。
"""

from __future__ import annotations

from typing import List, Optional

from ..core.models import Channel, Pattern, Song


def _default_groups(src_n: int, n: int) -> List[List[int]]:
    """よくあるチャンネル数の組み合わせに対する既定のグルーピング。"""
    if src_n == 8 and n == 4:
        # melody / bass / chord(2,3,4合成) / drums(5,6,7合成)
        return [[0], [1], [2, 3, 4], [5, 6, 7]]
    if src_n == 8 and n == 6:
        return [[0], [1], [2, 3, 4], [5], [6], [7]]
    if src_n == 8 and n == 5:
        return [[0], [1], [2, 3, 4], [5, 6], [7]]

    # 汎用フォールバック: 均等にチャンクへ分割する
    groups: List[List[int]] = [[] for _ in range(n)]
    for idx in range(src_n):
        groups[min(idx * n // src_n, n - 1)].append(idx)
    return groups


def remix_to_channels(song: Song, n: int,
                       groups: Optional[List[List[int]]] = None) -> Song:
    """Song を n チャンネルに縮約した新しい Song を返す（元の song は変更しない）。

    各グループ内では、同じ行で複数のイベントが競合した場合、グループ内で
    チャンネル番号が小さい方（＝役割として優先度が高い方）を採用する。
    """
    if n >= song.num_channels:
        return song

    groups = groups or _default_groups(song.num_channels, n)

    new_channels: List[Channel] = []
    for i, group in enumerate(groups):
        name = "+".join(song.channels[g].name for g in group)
        default_instrument = song.channels[group[0]].default_instrument
        is_drum = any(song.channels[g].is_drum_channel for g in group)
        new_channels.append(Channel(i, name, default_instrument, is_drum))

    new_patterns: List[Pattern] = []
    for pattern in song.patterns:
        new_pattern = Pattern(id=pattern.id, length=pattern.length)
        for i, group in enumerate(groups):
            new_pattern.ensure_channel(i)
            for row in range(pattern.length):
                chosen = None
                for g in group:
                    event = pattern.get_event(g, row)
                    if event is not None and not event.is_empty:
                        chosen = event
                        break
                new_pattern.rows[i][row] = chosen
        new_patterns.append(new_pattern)

    return Song(
        title=song.title,
        seed=song.seed,
        bpm=song.bpm,
        speed=song.speed,
        scale=song.scale,
        channels=new_channels,
        instruments=song.instruments,
        patterns=new_patterns,
        order=list(song.order),
        rows_per_pattern=song.rows_per_pattern,
    )
