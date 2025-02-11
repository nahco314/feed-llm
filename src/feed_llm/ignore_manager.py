"""Ignore manager for feed-llm.
All comments in English.

This module handles:
- Loading the default ignore patterns from 'default_ignores.txt'.
- Loading additional ignore patterns from '.feed-llm-ignore' in the target directory.
- Providing a function to decide whether a given path should be ignored.

If --no-ignore is given, these patterns are not used at all.
"""

from __future__ import annotations

import fnmatch
from pathlib import Path


def load_ignore_patterns(root_dir: Path, no_ignore: bool) -> list[str]:
    """
    Load ignore patterns from the default_ignores.txt resource and
    from .feed-llm-ignore in the root_dir, unless --no-ignore is True.

    :param root_dir: Target directory where .feed-llm-ignore might exist.
    :param no_ignore: If True, do not load or apply any ignore patterns.
    :return: A list of glob-like patterns for ignoring.
    """
    if no_ignore:
        return []

    patterns = []

    # 1) Load default ignore patterns (internal resource).
    default_file = Path(__file__).parent / "default_ignores.txt"
    if default_file.exists():
        try:
            with default_file.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        patterns.append(line)
        except Exception:
            pass  # Safety: ignore any file read error

    # 2) Load .feed-llm-ignore (if it exists) in the target directory.
    user_ignore = root_dir / ".feed-llm-ignore"
    if user_ignore.exists():
        try:
            with user_ignore.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        patterns.append(line)
        except Exception:
            pass

    return patterns


def should_ignore(path: Path, ignore_patterns: list[str]) -> bool:
    """
    Decide if 'path' should be ignored based on the given ignore patterns.

    This function does a filename-based match using fnmatch, i.e.:
    - If path.name matches any pattern (like '*.pyc' or '.git' etc.),
      then path is ignored (excluded).
    - For directories, a match on its name also excludes the entire subtree.

    :param path: The file or directory path to test.
    :param ignore_patterns: The patterns loaded from default_ignores.txt and/or .feed-llm-ignore.
    :return: True if 'path' should be ignored, False otherwise.
    """
    name = path.name
    for pattern in ignore_patterns:
        if fnmatch.fnmatch(name, pattern):
            return True
    return False
