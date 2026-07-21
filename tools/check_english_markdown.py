"""Verify that technical Markdown files are written in English (ADR-015).

Scans Markdown files in the technical directories for Cyrillic characters and fails if any are
found. The read-only source requirements under ``chatgpt_docs/`` are excluded, since they may
remain in Russian. Business/localization content lives outside these directories.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Directories (relative to the repo root) whose Markdown must be English.
TECHNICAL_DIRECTORIES = (
    "docs",
    "tasks",
    "services",
    "libs",
    "contracts",
    "orchestration",
    "infrastructure",
    "tools",
)

# Individual root-level Markdown files that must be English.
ROOT_FILES = ("README.md", "CLAUDE.md")

# Inclusive Unicode ranges covering Cyrillic characters.
_CYRILLIC_RANGES = ((0x0400, 0x04FF), (0x0500, 0x052F))


def _contains_cyrillic(text: str) -> bool:
    """Return whether a string contains any Cyrillic character.

    Args:
        text: The text to inspect.

    Returns:
        ``True`` if a Cyrillic character is present.
    """
    return any(any(start <= ord(char) <= end for start, end in _CYRILLIC_RANGES) for char in text)


def _iter_markdown_files(repo_root: Path) -> list[Path]:
    """Collect the Markdown files that must be validated.

    Args:
        repo_root: The repository root directory.

    Returns:
        A sorted list of Markdown file paths.
    """
    files: set[Path] = set()
    for directory in TECHNICAL_DIRECTORIES:
        files.update((repo_root / directory).rglob("*.md"))
    for name in ROOT_FILES:
        candidate = repo_root / name
        if candidate.exists():
            files.add(candidate)
    return sorted(files)


def find_violations(repo_root: Path) -> list[Path]:
    """Find technical Markdown files that contain Cyrillic characters.

    Args:
        repo_root: The repository root directory.

    Returns:
        The offending file paths.
    """
    violations: list[Path] = []
    for path in _iter_markdown_files(repo_root):
        if _contains_cyrillic(path.read_text(encoding="utf-8")):
            violations.append(path)
    return violations


def main() -> int:
    """Run the check and report violations.

    Returns:
        Process exit code: 0 when all files are English, 1 otherwise.
    """
    repo_root = Path(__file__).resolve().parents[1]
    violations = find_violations(repo_root)
    if violations:
        sys.stderr.write("Cyrillic found in technical Markdown (must be English, ADR-015):\n")
        for path in violations:
            sys.stderr.write(f"  - {path.relative_to(repo_root).as_posix()}\n")
        return 1
    sys.stdout.write("All technical Markdown files are English.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
