#!/usr/bin/env python3
"""Fail CI when unittest discovery silently finds too few tests."""

from __future__ import annotations

import argparse
import sys
import unittest
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--minimum", type=int, default=1)
    args = parser.parse_args()

    if args.minimum < 1:
        parser.error("--minimum must be at least 1")

    root = Path.cwd().resolve()
    sys.path.insert(0, str(root))
    discovered = unittest.defaultTestLoader.discover(str(root / "tests")).countTestCases()
    if discovered < args.minimum:
        print(
            f"discovered {discovered} tests, fewer than required {args.minimum}",
            file=sys.stderr,
        )
        return 1

    print(f"discovered {discovered} tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
