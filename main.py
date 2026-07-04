#!/usr/bin/env python3
"""TrackMaker CLI ―― 世界の音階でランダム作曲し、各種形式へ出力する。

使用例:
    python main.py --seed 1234 --out midi
    python main.py --out xm
    python main.py --out mod
    python main.py --out it
    python main.py --out s3m
    python main.py --out dmf
    python main.py --out all --config my_config.yaml
    python main.py --list-scales
"""

from __future__ import annotations

import argparse
import os
import sys

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    # Windows のコンソール既定コードページ（cp932等）では日本語出力が
    # 文字化けするため、可能なら標準出力をUTF-8に強制する。
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

from trackmaker.compose import generate_song
from trackmaker.config import load_config
from trackmaker.core.scale import list_scale_names
from trackmaker.export import EXPORTERS, EXTENSIONS


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="世界の音階からランダムに作曲し、MIDI/トラッカー形式で出力する。")
    parser.add_argument("--seed", type=int, default=None,
                         help="乱数シード（省略時はランダム）")
    parser.add_argument("--out", type=str, default="midi",
                         choices=list(EXPORTERS.keys()) + ["all"],
                         help="出力形式")
    parser.add_argument("--output-dir", type=str, default="output",
                         help="出力先ディレクトリ")
    parser.add_argument("--title", type=str, default=None,
                         help="曲タイトル（省略時は音階名から自動生成）")
    parser.add_argument("--scale", type=str, default=None,
                         help="音階名を強制指定（部分一致、省略時はランダム）")
    parser.add_argument("--config", type=str, default=None,
                         help="設定ファイル（YAML/JSON）へのパス")
    parser.add_argument("--list-scales", action="store_true",
                         help="利用可能な音階一覧を表示して終了する")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    if args.list_scales:
        for name in list_scale_names():
            print(name)
        return 0

    config = load_config(args.config)

    song = generate_song(seed=args.seed, title=args.title,
                          scale_name=args.scale, config=config)

    os.makedirs(args.output_dir, exist_ok=True)

    targets = list(EXPORTERS.keys()) if args.out == "all" else [args.out]

    safe_title = "".join(c if c.isalnum() else "_" for c in song.title)[:40]
    base_name = f"{safe_title}_seed{song.seed}"

    print(f"曲タイトル: {song.title}")
    print(f"音階: {song.scale.name} [{song.scale.culture}]"
          f"（{'和声進行' if song.scale.harmonic else 'ドローン＋旋律'}）")
    print(f"シード: {song.seed} / BPM: {song.bpm} / パターン数: {len(song.patterns)}")

    for fmt in targets:
        exporter = EXPORTERS[fmt]
        out_path = os.path.join(args.output_dir, f"{base_name}{EXTENSIONS[fmt]}")
        exporter(song, out_path)
        print(f"  -> [{fmt}] {out_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
