#!/usr/bin/env python3
"""Reject generated files, credentials, and machine paths in the Git index."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

ALLOWED_ENV_FILES = {".env.example"}
SECRET_PREFIXES = (
    "s" + "k-",
    "g" + "ho_",
    "g" + "hp_",
    "g" + "hs_",
    "g" + "hr_",
    "g" + "hu_",
    "github" + "_pat_",
    "s" + "b_" + "secret_",
)
SECRET_PATTERNS = tuple(
    re.compile(re.escape(prefix.encode()) + rb"[A-Za-z0-9_-]{16,}")
    for prefix in SECRET_PREFIXES
)
PRIVATE_KEY_PATTERN = re.compile(
    b"-----BEGIN " + rb"(?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----"
)
MACHINE_MARKERS = (
    ("/" + "Users" + "/").encode(),
    ("C:" + "\\" + "Users" + "\\").encode(),
    ("/" + "home" + "/" + "u" + "huru").encode(),
    ("u" + "huru").encode(),
)


def tracked_paths(root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        capture_output=True,
        check=True,
    )
    return [
        item.decode("utf-8", errors="surrogateescape")
        for item in result.stdout.split(b"\0")
        if item
    ]


def forbidden_path_reason(relative_path: str) -> str | None:
    parts = PurePosixPath(relative_path).parts
    name = parts[-1] if parts else ""
    if name.startswith(".env") and name not in ALLOWED_ENV_FILES:
        return "environment file"
    if ".vercel" in parts:
        return "Vercel local metadata"
    if "__pycache__" in parts or name.endswith((".pyc", ".pyo")):
        return "Python generated file"
    if any(part.endswith(".egg-info") for part in parts):
        return "Python package metadata"
    return None


def content_reason(content: bytes) -> str | None:
    if PRIVATE_KEY_PATTERN.search(content) or any(
        pattern.search(content) for pattern in SECRET_PATTERNS
    ):
        return "secret-like content"
    if any(marker in content for marker in MACHINE_MARKERS):
        return "machine-specific content"
    return None


def check_public_tree(root: Path) -> list[str]:
    problems: list[str] = []
    for relative_path in tracked_paths(root):
        path_reason = forbidden_path_reason(relative_path)
        if path_reason:
            problems.append(f"{relative_path}: tracked {path_reason}")
            continue

        path = root / relative_path
        if not path.is_file():
            continue
        detected_content = content_reason(path.read_bytes())
        if detected_content:
            problems.append(f"{relative_path}: {detected_content}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()

    root = args.root.resolve()
    try:
        problems = check_public_tree(root)
    except (OSError, subprocess.CalledProcessError) as error:
        print(f"public tree check could not run: {error}", file=sys.stderr)
        return 2

    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        return 1

    print("public tree check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
