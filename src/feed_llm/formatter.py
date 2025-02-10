"""Formatting strategies for output (Markdown / XML). All comments in English."""

from __future__ import annotations
from abc import ABC, abstractmethod
from pathlib import Path


class FormatterStrategy(ABC):
    """Abstract base class for different formatting strategies."""

    @abstractmethod
    def format_text_file(self, path: Path, content: str) -> str:
        """
        Format text file content.

        :param path: Path of the file.
        :param content: The text content of the file.
        :return: A formatted string representing the file content.
        """
        raise NotImplementedError()

    @abstractmethod
    def format_binary_file(self, path: Path) -> str:
        """
        Format a placeholder when the file is considered binary.

        :param path: Path of the file.
        :return: A formatted string representing the binary file warning.
        """
        raise NotImplementedError()


class MarkdownFormatter(FormatterStrategy):
    """Markdown formatting strategy."""

    def format_text_file(self, path: Path, content: str) -> str:
        """
        Format text file in Markdown style.

        :param path: File path.
        :param content: The text content of the file.
        :return: Markdown formatted string.
        """
        return f"## {path}\n```\n{content}\n```\n"

    def format_binary_file(self, path: Path) -> str:
        """
        Format a binary file placeholder in Markdown.

        :param path: File path.
        :return: Binary file placeholder string.
        """
        return f"## {path}\n<binary-file/>\n"


class XmlFormatter(FormatterStrategy):
    """XML formatting strategy."""

    def format_text_file(self, path: Path, content: str) -> str:
        """
        Format text file in XML style.

        :param path: File path.
        :param content: The text content of the file.
        :return: XML formatted string.
        """
        escaped_content = (
            content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        )
        return f"<file path='{path}'>\n{escaped_content}\n</file>\n"

    def format_binary_file(self, path: Path) -> str:
        """
        Format a binary file placeholder in XML.

        :param path: File path.
        :return: XML snippet indicating a binary file.
        """
        return f"<file path='{path}' is_binary='true'><binary-file/></file>\n"
