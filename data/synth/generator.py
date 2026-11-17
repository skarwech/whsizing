"""Synthetic data generator (F1), thin shim over `whsizing.synth` (the installed CLI shares it).

Example: uv run python data/synth/generator.py data/synth/profiles/ecom_mid.yaml --defects
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from whsizing.errors import WhsizingError
from whsizing.synth import synthesize


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="F1 synthetic data generator")
    parser.add_argument("profile", type=Path, help="profile YAML (data/synth/profiles/*.yaml)")
    parser.add_argument("--out", type=Path, help="output folder (default data/generated/<name>)")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--defects", action="store_true", help="inject the profile's defects")
    args = parser.parse_args(argv)
    out = args.out or Path("data/generated") / args.profile.stem
    try:
        paths = synthesize(args.profile, out, seed=args.seed, defects=args.defects)
    except WhsizingError as e:
        print(f"error: {e}", file=sys.stderr)
        return e.exit_code
    for path in paths:
        print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
