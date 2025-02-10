"""Textual-based TUI for selecting files and directories. All comments in English."""

from __future__ import annotations
from typing import Dict, List

from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.widgets import Static, Tree
from textual.widgets.tree import TreeNode as TextualTreeNode
from textual.widgets.tree import TreeNode
from textual.binding import Binding
from textual.reactive import reactive
from textual import events
from rich.text import Text
from rich.style import Style
import logging
from pathlib import Path

from feed_llm.ignore_manager import should_ignore

# Define three selection states:
# 0 = not selected, 1 = partially selected, 2 = fully selected


class FileSelectionTree(Tree[str]):
    """
    Tree widget for file selection with tri-state logic.
    Mouse behavior:
      - Click near "[ ]" toggles selection.
      - Otherwise, toggles expand/collapse.
    Keyboard behavior:
      - UP/DOWN: Move highlight.
      - ENTER: Toggle selection.
      - SPACE: Expand/Collapse.
    """

    BINDINGS = [
        Binding("up", "cursor_up", show=False),
        Binding("down", "cursor_down", show=False),
        Binding("enter", "toggle_selection", show=False),
        Binding("space", "toggle_expand_collapse", show=False),
    ]

    prefix_click_width = 4  # Characters from the line start used for "[ ] " area.
    click_field_width = 3  # Number of characters to consider for clicking.

    def __init__(
        self,
        root_dir: Path,
        saved_state: list[str] | None = None,
        ignore_patterns: list[str] | None = None,
    ) -> None:
        """
        Initialize the tree.

        :param root_dir: Starting directory.
        :param saved_state: Optional list of relative file paths to pre-select.
        :param ignore_patterns: Glob-like patterns for ignoring certain files/dirs.
        """
        super().__init__("File Selection")
        self.root_dir = root_dir
        self.saved_state = saved_state or []
        self.ignore_patterns = ignore_patterns or []
        self.node_to_path: dict[TextualTreeNode, Path] = {}
        self.node_to_depth: dict[TextualTreeNode, int] = {}
        self.path_to_node: dict[Path, TextualTreeNode] = {}
        self.path_to_state: dict[Path, int] = {}
        self.auto_expand = False

    def on_mount(self) -> None:
        """
        Build the tree structure upon mounting.
        """
        self.root.expand()
        self._build_tree(self.root, self.root_dir)
        self.cursor_line = 0

        # --- Restore saved state (if provided) ---
        for rel_path in self.saved_state:
            abs_path = self.root_dir / rel_path
            if abs_path in self.path_to_node:
                self.set_path_state(abs_path, 2)
                self.path_to_node[abs_path].refresh()

    def _build_tree(
        self, parent_node: TextualTreeNode, directory: Path, depth: int = 0
    ) -> None:
        """
        Recursively build the tree from a directory.
        Directories are labeled "[D] name", files "[F] name".
        Ignored paths are simply not added to the tree.
        """
        self.path_to_state[directory] = 0
        self.node_to_path[parent_node] = directory
        self.path_to_node[directory] = parent_node
        self.node_to_depth[parent_node] = depth

        try:
            entries: list[Path] = sorted(directory.iterdir())
        except (PermissionError, FileNotFoundError):
            return

        # Filter out ignored items
        entries = [e for e in entries if not should_ignore(e, self.ignore_patterns)]

        dirs = [e for e in entries if e.is_dir()]
        files = [e for e in entries if e.is_file()]

        for entry in dirs:
            node_label = entry.name
            new_node = parent_node.add(node_label, expand=False, allow_expand=True)
            self.path_to_state[entry] = 0
            self.node_to_path[new_node] = entry
            self.path_to_node[entry] = new_node
            self.node_to_depth[new_node] = depth + 1
            # Recursively build children
            self._build_tree(new_node, entry, depth + 1)

        for entry in files:
            node_label = entry.name
            leaf_node = parent_node.add_leaf(node_label)
            self.path_to_state[entry] = 0
            self.node_to_path[leaf_node] = entry
            self.path_to_node[entry] = leaf_node
            self.node_to_depth[leaf_node] = depth + 1

    def get_path_state(self, path: Path) -> int:
        return self.path_to_state.get(path, 0)

    def set_path_state(
        self,
        path: Path,
        state: int,
        propagate_to_children: bool = True,
        update_parent: bool = True,
    ) -> None:
        self.path_to_state[path] = state
        if path.is_dir() and propagate_to_children:
            self._propagate_state_to_children(path, state)
        if update_parent:
            self._update_parents(path)
        # Refresh the node (if it exists) to update the label
        node = self.path_to_node.get(path)
        if node is not None:
            node.refresh()

    def _propagate_state_to_children(self, path: Path, state: int) -> None:
        try:
            for child_path in path.iterdir():
                if child_path in self.path_to_state and state in (0, 2):
                    self.set_path_state(child_path, state, True, False)
        except Exception:
            pass  # In case of permission errors etc.

    def _update_parents(self, path: Path) -> None:
        parent_dir = path.parent
        if parent_dir == path:
            return
        if parent_dir in self.path_to_state:
            child_states = self._collect_child_states(parent_dir)
            if child_states and all(s == 2 for s in child_states):
                self.set_path_state(parent_dir, 2, False, False)
            elif child_states and all(s == 0 for s in child_states):
                self.set_path_state(parent_dir, 0, False, False)
            else:
                self.set_path_state(parent_dir, 1, False, False)
            node = self.path_to_node.get(parent_dir)
            if node is not None:
                node.refresh()
            self._update_parents(parent_dir)

    def _collect_child_states(self, parent_path: Path) -> list[int]:
        states = []
        try:
            for entry in parent_path.iterdir():
                if entry in self.path_to_state:
                    states.append(self.path_to_state[entry])
        except Exception:
            pass
        return states

    def toggle_selection(self, node: TextualTreeNode) -> None:
        path = self.node_to_path[node]
        current_state = self.get_path_state(path)
        if current_state in (0, 1):
            self.set_path_state(path, 2)
        else:
            self.set_path_state(path, 0)
        node.refresh()

    def toggle_expand_collapse(self, node: TextualTreeNode) -> None:
        if node.allow_expand:
            node.toggle()
            self.refresh(layout=True)

    def render_label(
        self, node: TextualTreeNode, base_style: Style, style: Style
    ) -> Text:
        path = self.node_to_path[node]
        state = self.path_to_state[path]
        icon = "📂" if path.is_dir() else "📄"
        prefix = "[ ] " if state == 0 else "[x] " if state == 2 else "[-] "
        return Text.assemble(
            prefix,
            f"{icon} {node.label}",
            style=style,
        )

    async def _on_click(self, event: events.Click) -> None:
        async with self.lock:
            meta = event.style.meta
            if "line" not in meta:
                return
            cursor_line = meta["line"]
            if not meta.get("toggle", False):
                self.cursor_line = cursor_line
                await self.run_action("select_cursor")
            node = self.get_node_at_line(cursor_line)
            if node is None:
                return
            x = event.x
            x_offset = self.node_to_depth[node] * self.prefix_click_width
            if x_offset <= x < x_offset + self.click_field_width:
                self.toggle_selection(node)
            else:
                self.toggle_expand_collapse(node)

    def action_cursor_up(self) -> None:
        self.cursor_line = max(0, self.cursor_line - 1)
        self.scroll_to_line(self.cursor_line)

    def action_cursor_down(self) -> None:
        if self.cursor_line < self.last_line:
            self.cursor_line += 1
            self.scroll_to_line(self.cursor_line)

    def action_toggle_selection(self) -> None:
        node = self.cursor_node
        if node is not None:
            self.toggle_selection(node)
            self.refresh(layout=True)

    def action_toggle_expand_collapse(self) -> None:
        node = self.cursor_node
        if node is not None:
            self.toggle_expand_collapse(node)
            self.refresh(layout=True)


class FileSelectionApp(App[None]):
    """
    A Textual App displaying a file selection tree.
    Pressing 'q' quits normally (saving state), while 'ctrl+q' aborts (state remains unchanged).
    """

    CSS = """
    Screen {
        layout: vertical;
    }
    """

    BINDINGS = [
        Binding("q", "quit_app", "Quit"),
        Binding("ctrl+q", "abort_app", "Abort (do not save state)"),
    ]

    def __init__(
        self,
        root_dir: Path,
        saved_state: list[str] | None = None,
        ignore_patterns: list[str] | None = None,
    ) -> None:
        super().__init__()
        self.root_dir: Path = root_dir
        self.file_tree: FileSelectionTree = FileSelectionTree(
            root_dir, saved_state=saved_state, ignore_patterns=ignore_patterns
        )
        self.selected_paths: list[Path] = []
        self.save_state: bool = True  # True -> save new state on exit; False -> keep previous state

    def compose(self) -> ComposeResult:
        with Vertical():
            yield self.file_tree
            yield Static(
                "UP/DOWN: move, ENTER: select/unselect, SPACE: expand/collapse, Q: quit, CTRL+Q: abort\n"
                "Mouse: click [ ] to toggle selection, click elsewhere to expand/collapse.\n"
                "Directories are labeled [D], files labeled [F].",
                id="footer",
            )

    def action_quit_app(self) -> None:
        """
        Quit normally: collect selection states and exit.
        """
        self.selected_paths = self._collect_selected_files()
        self.exit()

    def action_abort_app(self) -> None:
        """
        Abort exit via ctrl+q: do not update saved state.
        """
        self.save_state = False
        self.exit()

    def _collect_selected_files(self) -> list[Path]:
        results: list[Path] = []
        for path, state in self.file_tree.path_to_state.items():
            # If fully selected (2) and it's actually a file (not a dir)
            if state == 2 and not path.is_dir():
                results.append(path)
        return results


def run_file_selection_app(
    directory: Path,
    saved_state: list[str] | None = None,
    ignore_patterns: list[str] | None = None,
) -> tuple[list[Path], bool]:
    """
    Instantiate and run FileSelectionApp.
    Returns a tuple: (list of selected file paths, save_state flag).

    :param directory: Root directory to browse.
    :param saved_state: Previously selected file paths (relative).
    :param ignore_patterns: Patterns to ignore.
    :return: (selected file paths, whether to save new state)
    """
    app = FileSelectionApp(directory, saved_state=saved_state, ignore_patterns=ignore_patterns)
    app.run()
    return app.selected_paths, app.save_state
