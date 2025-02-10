"""CLI entry point using cyclopts. All comments in English."""

from __future__ import annotations
import logging
import mimetypes
from pathlib import Path
from typing import Literal

import cyclopts
import json
import hashlib
import os
import sys

import feed_llm.ui

# --- Module-level cache for the save directory ---
_STATE_DIR: Path | None = None


# --- State persistence helper functions ---
def _get_save_dir() -> Path:
    """
    Determine the dedicated save directory for feed-llm state based on platform.
    Windows: %APPDATA%/feed-llm
    macOS: ~/Library/Application Support/feed-llm
    Linux: ~/.config/feed-llm
    Logged only once per process.
    """
    global _STATE_DIR
    if _STATE_DIR is not None:
        return _STATE_DIR

    if os.name == "nt":
        base = Path(os.getenv("APPDATA", Path.home()))
        save_dir = base / "feed-llm"
    elif sys.platform == "darwin":
        save_dir = Path.home() / "Library" / "Application Support" / "feed-llm"
    else:
        save_dir = Path.home() / ".config" / "feed-llm"
    save_dir.mkdir(parents=True, exist_ok=True)
    _STATE_DIR = save_dir
    logging.info(f"Using state directory: {save_dir}")
    return save_dir


def _get_state_file(directory: Path) -> Path:
    """
    For a given target directory, compute a state file path inside the save directory.
    The file name is based on the MD5 hash of the directory's absolute path.
    """
    resolved = directory.resolve()
    hash_digest = hashlib.md5(str(resolved).encode("utf-8")).hexdigest()
    state_file = _get_save_dir() / f"{hash_digest}.json"
    return state_file


def _load_state(directory: Path) -> list[str]:
    """
    Load saved state for the given directory.
    Returns a list of relative file paths (as strings) that were selected previously.
    """
    state_file = _get_state_file(directory)
    if state_file.exists():
        try:
            with state_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
            saved = data.get("selected_files", [])
            return saved
        except Exception as e:
            logging.warning(f"Failed to load state from {state_file}: {e}")
            return []
    else:
        return []


def _save_state(directory: Path, selected_paths: list[Path]) -> None:
    """
    Save the selected file state for the given directory.
    The selected_paths are converted to paths relative to 'directory' and stored as JSON.
    """
    state_file = _get_state_file(directory)
    try:
        rel_paths = [str(p.relative_to(directory)) for p in selected_paths]
    except ValueError:
        rel_paths = [str(p) for p in selected_paths]
    data = {"selected_files": rel_paths}
    try:
        with state_file.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logging.error(f"Failed to save state to {state_file}: {e}")


# --- Main Application Entry Point ---
def app_main(
    directory: str = ".",
    stdout: bool = False,
    format_: Literal["markdown", "xml"] = "markdown",
) -> None:
    """
    Main CLI entry point.
    Uses the textual TUI for file selection, then outputs the selected files (formatted as text or binary placeholder).
    Also restores previous selection state (if available) and saves state on normal exit.
    If the user quits via ctrl+q, the saved state remains unchanged.
    """
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    target_dir = Path(directory)

    # Load previous state (if any) from the dedicated save directory.
    previous_state = _load_state(target_dir)

    # Run the TUI to get selected file paths, passing in the saved state.
    # The TUI returns a tuple: (selected_paths, save_flag)
    try:
        selected_paths, save_flag = feed_llm.ui.run_file_selection_app(
            target_dir, saved_state=previous_state
        )
    except KeyboardInterrupt:
        return

    if selected_paths is None:
        logging.info("No files selected. Exiting.")
        return

    # Decide which formatter to use.
    if format_ == "markdown":
        from feed_llm.formatter import MarkdownFormatter as Formatter
    else:
        from feed_llm.formatter import XmlFormatter as Formatter

    formatter = Formatter()

    # Prepare the output.
    formatted_files: list[str] = []
    warn_binary_paths: list[Path] = []

    for path in selected_paths:
        if _is_text_file(path):
            content = _read_file_content(path)
            formatted_files.append(formatter.format_text_file(path, content))
        else:
            warn_binary_paths.append(path)
            formatted_files.append(formatter.format_binary_file(path))

    for bp in warn_binary_paths:
        logging.warning(f"Selected binary file: {bp}")

    final_output = "\n".join(formatted_files)

    if stdout:
        print(final_output)
    else:
        try:
            import pyperclip

            pyperclip.copy(final_output)
            logging.info("Output has been copied to clipboard.")
        except ImportError:
            logging.warning("pyperclip is not installed. Printing to stdout.")
            print(final_output)

    # --- Save state only on normal exit (via 'q') ---
    if save_flag:
        _save_state(target_dir, selected_paths)
    else:
        pass


def _is_text_file(path: Path, read_bytes: int = 1024) -> bool:
    """
    Rough detection of text vs. binary by reading a small portion of the file.
    Uses mimetypes first; otherwise checks for zero bytes or non-ASCII content.
    """
    mime, _ = mimetypes.guess_type(path)
    if mime is not None and (mime.startswith("text/") or mime == "application/xml"):
        return True

    try:
        with open(path, "rb") as f:
            chunk = f.read(read_bytes)
        if b"\0" in chunk:
            return False
        non_ascii = sum(b > 127 for b in chunk)
        ratio = non_ascii / len(chunk) if chunk else 0
        return ratio < 0.30
    except OSError:
        return False


def _read_file_content(path: Path) -> str:
    """
    Read the entire content of a text file.
    """
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return "(Could not read file)"


def main():
    cyclopts.run(app_main)


if __name__ == "__main__":
    main()
