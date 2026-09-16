"""Style checks for every tracked text file.

Two rules, both cheap to break by accident and annoying to spot in review:

1. No em or en dash characters. The project writes plain hyphens and commas.
2. No machine-specific home directory paths, which tend to leak in through
   pasted logs and editor config.

Uses `git ls-files` when the tree is a git checkout, so ignored files such as
`.env` and `storage/` are never read. Exits 1 and lists every hit otherwise.

    python scripts/check_text.py
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {
    ".py", ".md", ".txt", ".toml", ".yml", ".yaml", ".json", ".jsonl",
    ".js", ".jsx", ".css", ".html", ".svg", ".cfg", ".ini", ".example",
}
TEXT_NAMES = {"Dockerfile", "Makefile", ".gitignore", ".dockerignore", ".gitattributes", ".editorconfig"}
SKIP_PARTS = {".git", ".venv", "venv", "node_modules", "dist", "storage", "__pycache__"}

DASHES = re.compile("[\u2013\u2014]")
# A Windows user profile, /home/<name>, or /Users/<name>. Placeholders in angle
# brackets are fine, and a line can opt out with "check_text: allow".
HOME_PATH = re.compile(r"(?i)\b[a-z]:\\users\\(?!<)[^\\\s]+|(?<![\w.])/(?:home|Users)/(?!<)[a-z][\w.-]+/")


def tracked_files() -> list[Path]:
    try:
        out = subprocess.run(
            ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout
        return [ROOT / line for line in out.splitlines() if line]
    except (OSError, subprocess.CalledProcessError):
        return [p for p in ROOT.rglob("*") if p.is_file() and not SKIP_PARTS & set(p.parts)]


def is_text(path: Path) -> bool:
    return path.suffix.lower() in TEXT_SUFFIXES or path.name in TEXT_NAMES


def main() -> int:
    problems: list[str] = []
    for path in tracked_files():
        if not path.is_file() or not is_text(path):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        rel = path.relative_to(ROOT).as_posix()
        for number, line in enumerate(text.splitlines(), 1):
            if DASHES.search(line):
                problems.append(f"{rel}:{number}: em or en dash, use a hyphen or a comma")
            if HOME_PATH.search(line) and "check_text: allow" not in line:
                problems.append(f"{rel}:{number}: machine-specific home directory path")
    if problems:
        print("\n".join(problems))
        print(f"\n{len(problems)} problem(s) found.")
        return 1
    print("Text checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
