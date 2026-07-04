"""設定ファイル（YAML/JSON）の読み込みとデフォルト値。

設定ファイルは任意（--config 未指定時は DEFAULT_CONFIG のみを使用）。
YAML を使う場合は PyYAML が必要（未インストールなら JSON を使うか、
pip install pyyaml でインストールする）。
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

DEFAULT_CONFIG: Dict[str, Any] = {
    # パターン長（行数）とパターン数
    "rows_per_pattern": 64,
    "num_patterns": 4,
    # テンポ（BPM）の抽選範囲
    "bpm_min": 90,
    "bpm_max": 160,
    # 1行あたりのティック数（トラッカー用語での speed）
    "speed": 6,
    # 和音/ドローンを切り替える間隔（行数）
    "chord_change_rows": 16,
    # ベースを打ち直す間隔（行数）
    "bass_pulse_rows": 4,
    # 基音（root）を抽選する MIDI ノート番号の範囲
    "root_note_min": 48,
    "root_note_max": 64,
    # 内部モデルで常に使うチャンネル数
    # (0:melody 1:bass 2-4:chord/drone 5:kick 6:snare 7:hihat)
    "internal_channels": 8,
}


def load_config(path: Optional[str]) -> Dict[str, Any]:
    """設定ファイルを読み込み、DEFAULT_CONFIG にマージして返す。

    Args:
        path: .yaml/.yml または .json ファイルへのパス。None ならデフォルトのみ。
    """
    config = dict(DEFAULT_CONFIG)
    if not path:
        return config

    if not os.path.exists(path):
        raise FileNotFoundError(f"設定ファイルが見つかりません: {path}")

    ext = os.path.splitext(path)[1].lower()
    with open(path, "r", encoding="utf-8") as f:
        if ext in (".yaml", ".yml"):
            try:
                import yaml  # type: ignore
            except ImportError as exc:
                raise ImportError(
                    "YAML設定ファイルを使うには PyYAML が必要です: pip install pyyaml"
                ) from exc
            user_config = yaml.safe_load(f) or {}
        elif ext == ".json":
            user_config = json.load(f)
        else:
            raise ValueError(f"未対応の設定ファイル形式です: {ext}")

    config.update(user_config)
    return config
