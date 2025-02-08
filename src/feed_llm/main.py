"""CLI entry point using cyclopts. All comments in English."""

from __future__ import annotations
import logging
import mimetypes
from pathlib import Path
from typing import Literal

import cyclopts

import feed_llm.ui

from feed_llm.formatter import MarkdownFormatter, XmlFormatter


def app_main(directory: str = ".", stdout: bool = False, format_: Literal["markdown", "xml"] = "markdown") -> None:
    """
    Main CLI entry point. Uses the textual TUI for file selection,
    then outputs the selected files (in text format or a binary placeholder).
    By default, copies to clipboard unless --stdout is specified.
    """
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    # Run the TUI to get selected file paths
    selected_paths = feed_llm.ui.run_file_selection_app(Path(directory))

    if not selected_paths:
        logging.info("No files selected. Exiting.")
        return

    # Decide which formatter to use
    if format_ == "markdown":
        formatter = MarkdownFormatter()
    else:
        formatter = XmlFormatter()

    # Prepare the output
    formatted_files: list[str] = []
    warn_binary_paths: list[Path] = []

    for path in selected_paths:
        if _is_text_file(path):
            content = _read_file_content(path)
            formatted_files.append(formatter.format_text_file(path, content))
        else:
            # Mark as binary
            warn_binary_paths.append(path)
            formatted_files.append(formatter.format_binary_file(path))

    # Log warnings for binary files
    for bp in warn_binary_paths:
        logging.warning(f"Selected binary file: {bp}")

    final_output = "\n".join(formatted_files)

    if stdout:
        print(final_output)
    else:
        # Copy to clipboard. If pyperclip is unavailable, fallback to stdout
        try:
            import pyperclip
            pyperclip.copy(final_output)
            logging.info("Output has been copied to clipboard.")
        except ImportError:
            logging.warning("pyperclip is not installed. Printing to stdout.")
            print(final_output)


def _is_text_file(path: Path, read_bytes: int = 1024) -> bool:
    """
    Rough detection of text vs. binary by reading a small portion of the file
    and checking for zero bytes or extremely non-ASCII content.
    Alternatively, uses 'mimetypes' as a fallback.
    """
    # Try mimetypes first
    mime, _ = mimetypes.guess_type(path)
    if mime is not None and (mime.startswith("text/") or mime == "application/xml"):
        return True

    try:
        with open(path, "rb") as f:
            chunk = f.read(read_bytes)
        if b"\0" in chunk:
            return False
        # Heuristic: if 30% or more of the bytes are outside ASCII range, consider it binary
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
