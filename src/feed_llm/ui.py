"""Textual-based TUI for selecting files and directories. All comments in English."""

from __future__ import annotations
from typing import Dict

from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.widgets import Static, Tree
from textual.widgets.tree import TreeNode as TextualTreeNode
from textual.widgets.tree import TreeNode
from textual.binding import Binding
from textual.reactive import reactive
from textual import events
from textual.message import Message
from rich.text import Text
from rich.style import Style
import logging
from pathlib import Path

# We define three states for selection:
# 0 = not selected
# 1 = partially selected
# 2 = fully selected


class FileSelectionTree(Tree[str]):
    """
    A tree widget to display and manage file selections with tri-state
    (not selected, partially selected, fully selected).

    Mouse behavior:
    - If user clicks near the prefix "[ ]", we toggle selection state.
    - Otherwise, we toggle expand/collapse.

    Keyboard behavior:
    - UP/DOWN: Move highlight
    - ENTER: Toggle selection
    - SPACE: Expand/Collapse
    """

    # We override default bindings to ensure we handle arrow keys and space/enter
    BINDINGS = [
        Binding("up", "cursor_up", show=False),
        Binding("down", "cursor_down", show=False),
        Binding("enter", "toggle_selection", show=False),
        Binding("space", "toggle_expand_collapse", show=False),
    ]

    prefix_click_width = (
        4  # number of characters from the line start used for "[ ] " area
    )
    click_field_width = 3  # number of characters to consider for clicking

    def __init__(self, root_dir: Path) -> None:
        super().__init__("File Selection")
        self.root_dir = root_dir
        # We store the tree node -> path mapping to know the actual path of each node.
        self.node_to_path: dict[TextualTreeNode, Path] = {}
        # We store the node -> depth mapping to know the depth of each node.
        self.node_to_depth: dict[TextualTreeNode, int] = {}
        # Also, we store the path -> node mapping. It may be missing for some nodes.
        self.path_to_node: dict[Path, TextualTreeNode] = {}
        # path_to_state will map a filesystem path to an integer (0, 1, or 2).
        self.path_to_state: dict[Path, int] = {}

        # We want to handle expansion manually
        self.auto_expand = False

    def on_mount(self) -> None:
        """
        Called automatically when the widget is added to the app.
        We build the tree structure starting from the given root directory.
        """
        self.root.expand()
        self._build_tree(self.root, self.root_dir)
        # Optionally set the cursor to top
        self.cursor_line = 0

    def _build_tree(self, parent_node: TextualTreeNode, directory: Path, depth: int = 0) -> None:
        """
        Recursively build the tree from a directory.
        We show directories first, then files.
        Directories labeled "[D] name", files labeled "[F] name".
        
        Args:
            parent_node: The parent node to add children to
            directory: The directory path to build from
            depth: Current depth in the tree (0 for root)
        """
        self.path_to_state[directory] = 0  # initially not selected
        self.node_to_path[parent_node] = directory
        self.path_to_node[directory] = parent_node
        self.node_to_depth[parent_node] = depth  # Store the depth of this node

        try:
            entries: list[Path] = sorted(directory.iterdir())
        except (PermissionError, FileNotFoundError):
            return

        # separate directories and files
        dirs = [e for e in entries if e.is_dir()]
        files = [e for e in entries if e.is_file()]

        # 1. add directories
        for entry in dirs:
            full_path = entry
            node_label = f"[D] {entry}"
            new_node = parent_node.add(node_label, expand=False, allow_expand=True)
            self.path_to_state[full_path] = 0
            self.node_to_path[new_node] = full_path
            self.path_to_node[full_path] = new_node
            # Recursively build with incremented depth
            self._build_tree(new_node, full_path, depth + 1)

        # 2. add files
        for entry in files:
            full_path = entry
            node_label = f"[F] {entry}"
            leaf_node = parent_node.add_leaf(node_label)
            self.path_to_state[full_path] = 0
            self.node_to_path[leaf_node] = full_path
            self.path_to_node[full_path] = leaf_node
            self.node_to_depth[leaf_node] = depth + 1  # Store the depth of leaf nodes

    def get_path_state(self, path: Path) -> int:
        """Return the selection state of the path."""
        return self.path_to_state.get(path, 0)

    def set_path_state(
        self,
        path: Path,
        state: int,
        propagate_to_children: bool = True,
        update_parent: bool = True,
    ) -> None:
        """
        Set the selection state of a path, and also update parent/child states accordingly.
        Then refresh the view.
        """
        self.path_to_state[path] = state
        # If it's a directory, propagate to children
        if path.is_dir() and propagate_to_children:
            self._propagate_state_to_children(path, state)

        # Then, update parents up to the root
        if update_parent:
            self._update_parents(path)

        # Refresh display so that label is updated with new prefix
        self.path_to_node[path].refresh()

    def _propagate_state_to_children(self, path: Path, state: int) -> None:
        """
        Propagate a directory's state to all children. If 'state' is 2 (fully selected),
        then all children become fully selected. If 'state' is 0, all children become unselected.
        """
        for child_path in path.iterdir():
            if state in (0, 2) and child_path in self.path_to_state:
                self.set_path_state(child_path, state, True, False)

    def _update_parents(self, path: Path) -> None:
        """
        Walk upwards to parents and compute their states from their children.
        """
        parent_dir = path.parent
        if parent_dir == path:
            return

        if parent_dir in self.path_to_state:
            child_states = self._collect_child_states(parent_dir)
            if child_states and all(s == 2 for s in child_states):
                self.set_path_state(parent_dir, 2, False)
            elif child_states and all(s == 0 for s in child_states):
                self.set_path_state(parent_dir, 0, False)
            else:
                self.set_path_state(parent_dir, 1, False)

            # Recursively update parent's parent
            self._update_parents(parent_dir)

    def _collect_child_states(self, parent_path: Path) -> list[int]:
        """
        Collect all immediate children's states for a directory.
        """
        states = []
        for entry in parent_path.iterdir():
            full_path = entry
            states.append(self.path_to_state.get(full_path, 0))
        return states

    def toggle_selection(self, node: TextualTreeNode) -> None:
        """
        Toggle the selection of the node's associated path.
        If directory is partially or not selected, it becomes fully selected.
        If fully selected, it becomes not selected.
        """
        path = self.node_to_path[node]
        current_state = self.get_path_state(path)
        if current_state in (0, 1):
            self.set_path_state(path, 2)
        else:
            self.set_path_state(path, 0)
        node.refresh()

    def toggle_expand_collapse(self, node: TextualTreeNode) -> None:
        """
        Toggle expand/collapse of the node.
        """
        if node.allow_expand:
            node.toggle()
            self.refresh(layout=True)

    # -----------------------------
    # Rendering (prefix + [D]/[F])
    # -----------------------------
    def render_label(
        self, node: TextualTreeNode, base_style: Style, style: Style
    ) -> Text:
        """
        Override to display selection state as part of the label.
        e.g. [ ] / [x] / [-] + "[D]" or "[F]"
        """
        path = self.node_to_path[node]
        state = self.path_to_state[path]

        if state == 0:
            prefix = "[ ] "
        elif state == 2:
            prefix = "[x] "
        else:
            prefix = "[-] "

        # The node.label might already contain "[D]" or "[F]" from _build_tree
        label_text = Text.assemble(prefix, node.label, style=style)
        return label_text

    # -----------------------------
    # Mouse events
    # -----------------------------
    async def _on_click(self, event: events.Click) -> None:
        """
        Available in Textual 0.14+.
        We check the x coordinate to see if user clicked in the "prefix" region or not.
        """

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

    # -----------------------------
    # Keyboard actions
    # -----------------------------
    def action_cursor_up(self) -> None:
        """Move the cursor (highlight) up by 1 node."""
        self.cursor_line = max(0, self.cursor_line - 1)
        self.scroll_to_line(self.cursor_line)

    def action_cursor_down(self) -> None:
        """Move the cursor (highlight) down by 1 node."""
        if self.cursor_line < self.last_line:
            self.cursor_line += 1
            self.scroll_to_line(self.cursor_line)

    def action_toggle_selection(self) -> None:
        """Toggle selection of the currently highlighted node, then refresh."""
        node = self.cursor_node
        if node is not None:
            self.toggle_selection(node)
            self.refresh(layout=True)

    def action_toggle_expand_collapse(self) -> None:
        """Toggle expansion of the currently highlighted node, then refresh."""
        node = self.cursor_node
        if node is not None:
            self.toggle_expand_collapse(node)
            self.refresh(layout=True)


class FileSelectionApp(App[None]):
    """
    A Textual App that displays a file selection tree. On pressing 'q',
    the app exits and you can retrieve the selected files from `self.selected_paths`.
    """

    CSS = """
    Screen {
        layout: vertical;
    }
    """

    BINDINGS = [
        Binding("q", "quit_app", "Quit"),
    ]

    def __init__(self, root_dir: Path) -> None:
        super().__init__()
        self.root_dir: Path = root_dir
        self.file_tree: FileSelectionTree = FileSelectionTree(root_dir)
        self.selected_paths: list[Path] = []

    def compose(self) -> ComposeResult:
        """
        Compose the layout with a vertical container:
         - The Tree view
         - A footer with instructions
        """
        with Vertical():
            yield self.file_tree
            yield Static(
                "UP/DOWN: move, ENTER: select/unselect, SPACE: expand/collapse, Q: quit\n"
                "Mouse: click [ ] to toggle selection, click elsewhere on the node to expand/collapse.\n"
                "Directories are labeled [D], files labeled [F].",
                id="footer",
            )

    def action_quit_app(self) -> None:
        """
        Action triggered by pressing 'q'. Collect selection states, store them, then exit.
        """
        self.selected_paths = self._collect_selected_files()
        self.exit()

    def _collect_selected_files(self) -> list[Path]:
        """
        Collect all paths that are fully selected (state=2) and are not directories,
        i.e. actual files. Return them as a list.
        """
        results: list[Path] = []
        for path, state in self.file_tree.path_to_state.items():
            if state == 2:
                if not path.is_dir():
                    results.append(path)
        return results

    def on_tree_node_selected(self, event: Tree.NodeSelected[str]) -> None:
        """
        When the user presses ENTER on a node. We toggle selection state here.
        """
        node = event.node
        self.file_tree.toggle_selection(node)
        self.file_tree.refresh(layout=True)

    def on_tree_node_expanded(self, event: Tree.NodeExpanded[str]) -> None:
        """
        Called when a node is expanded by SPACE.
        We'll refresh the tree to ensure states are correctly displayed.
        """
        self.file_tree.refresh(layout=True)

    def on_tree_node_collapsed(self, event: Tree.NodeCollapsed[str]) -> None:
        """
        Called when a node is collapsed by SPACE.
        We'll refresh the tree to ensure states are correctly displayed.
        """
        self.file_tree.refresh(layout=True)


def run_file_selection_app(directory: Path) -> list[Path]:
    """
    Helper function to instantiate and run FileSelectionApp. Returns the selected file paths.

    :param directory: Directory to display in the TUI.
    :return: List of selected file paths.
    """
    app = FileSelectionApp(directory)
    app.run()
    return app.selected_paths
