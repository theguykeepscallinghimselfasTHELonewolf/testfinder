import os
import csv
import json
from pathlib import Path
from textual.app import App, ComposeResult
from textual.widgets import Tree, Footer, Header, Input, Label, Static
from textual.containers import Vertical, Horizontal
from textual.screen import Screen, ModalScreen
from textual.binding import Binding
from rich.text import Text

# --- MODAL: For capturing reasons ---
class ReasonModal(ModalScreen[str]):
    """A modal dialog to ask the user why they are changing a file's status."""
    
    CSS = """
    ReasonModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }
    #dialog {
        width: 60%;
        height: auto;
        padding: 2 4;
        background: $surface;
        border: thick $primary;
    }
    Input { margin-top: 1; }
    """

    def __init__(self, filename: str, prompt_text: str):
        super().__init__()
        self.filename = filename
        self.prompt_text = prompt_text

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(f"[bold yellow]{self.prompt_text}[/bold yellow]\n{self.filename}")
            yield Label("\nProvide a reason: (Press Enter to submit)")
            yield Input(placeholder="e.g., Dummy fixture, Config file, Vendor folder...", id="reason-input")

    def on_mount(self) -> None:
        self.query_one(Input).focus()

    def on_key(self, event) -> None:
        # THE FIX: Stop the Tree widget from stealing the spacebar while typing!
        if event.key == "space":
            event.stop()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value)


# --- SCREEN 1: Review Auto-Detected Files ---
class ReviewScreen(Screen):
    BINDINGS = [
        Binding("t", "toggle_state", "Toggle [False Positive]"),
        Binding("n", "next_screen", "Next: Browse Full Repo ➡️"),
        Binding("c", "confirm", "Finish & Save"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Label(" 🔍 [bold underline]Step 1: Review Auto-Detected Tests[/bold underline]\n (Press Enter/Right Arrow to see details, 't' to flag as False Positive)", classes="screen-title")
        yield Tree("Auto-Detected Files", id="review-tree")
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_tree()
        
    def on_screen_resume(self) -> None:
        self.refresh_tree()

    def format_label(self, path_str: str, rel_path: str) -> Text:
        state = self.app.state_map.get(path_str)
        if state == "DETECTED":
            return Text.from_markup(f"[bold green]☑[/bold green] 📄 {rel_path}")
        elif state == "FALSE_POSITIVE":
            return Text.from_markup(f"[bold red]☐[/bold red] 📄 [strike]{rel_path}[/strike] [dim red](False Positive)[/dim red]")
        return Text(rel_path)

    def refresh_tree(self) -> None:
        tree = self.query_one("#review-tree", Tree)
        tree.clear()
        tree.root.expand()
        
        for abs_path, data in self.app.findings_map.items():
            rel_path = str(Path(abs_path).relative_to(self.app.project_root))
            label = self.format_label(abs_path, rel_path)
            
            node = tree.root.add(label, data={"path": abs_path, "is_dir": False})
            
            node.add_leaf(f"🎯 Hits: {data.get('hit_count', 0)}")
            node.add_leaf(f"🛠️  Frameworks: {', '.join(data.get('frameworks', []))}")
            node.add_leaf(f"🏷️  Triggers: {', '.join(data.get('reasons', []))}")
            
            if self.app.state_map.get(abs_path) == "FALSE_POSITIVE":
                reason = self.app.reasons.get(abs_path, "No reason provided")
                node.add_leaf(f"📝 Reason: [red]{reason}[/red]")

    def action_toggle_state(self) -> None:
        tree = self.query_one("#review-tree", Tree)
        node = tree.cursor_node
        if not node or not node.data or "path" not in node.data:
            return

        path_str = node.data["path"]
        path_obj = Path(path_str)
        current_state = self.app.state_map.get(path_str)

        if current_state == "DETECTED":
            def set_false_positive(reason: str):
                self.app.state_map[path_str] = "FALSE_POSITIVE"
                self.app.reasons[path_str] = reason
                self.refresh_tree()
            self.app.push_screen(ReasonModal(path_obj.name, "Flagging Auto-Detected File as False Positive"), set_false_positive)
        elif current_state == "FALSE_POSITIVE":
            self.app.state_map[path_str] = "DETECTED"
            self.refresh_tree()

    def action_next_screen(self) -> None:
        self.app.switch_screen("browse")

    def action_confirm(self) -> None:
        self.app.finalize_and_exit()


# --- SCREEN 2: Browse Full Repo (Split Screen) ---
class BrowseScreen(Screen):
    CSS = """
    #main-container { height: 1fr; }
    #tree-pane { width: 50%; height: 100%; border-right: solid $primary; padding: 0 1; }
    #list-pane { width: 50%; height: 100%; padding: 1 2; overflow-y: auto; background: $surface; }
    """

    BINDINGS = [
        Binding("t", "toggle_state", "Toggle Selection"),
        Binding("b", "back_screen", "⬅️ Back to Review"),
        Binding("c", "confirm", "Finish & Save"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Label(" 📁 [bold underline]Step 2: Browse Full Repository[/bold underline]\n (Add missing files/directories to the exclusion list)", classes="screen-title")
        with Horizontal(id="main-container"):
            with Vertical(id="tree-pane"):
                tree = Tree(f"📦 {self.app.project_root.name}", id="browse-tree")
                tree.root.data = {"path": str(self.app.project_root), "is_dir": True}
                yield tree
            with Vertical(id="list-pane"):
                yield Static("Loading...", id="live-list")
        yield Footer()

    def on_mount(self) -> None:
        tree = self.query_one("#browse-tree", Tree)
        tree.root.expand()
        self.load_directory(tree.root)
        self.update_live_list()

    def on_screen_resume(self) -> None:
        self.update_live_list()
        tree = self.query_one("#browse-tree", Tree)
        self.sync_tree_labels(tree.root)

    def sync_tree_labels(self, node):
        if node.data and "path" in node.data and node != self.query_one("#browse-tree", Tree).root:
            path_str = node.data["path"]
            is_dir = node.data["is_dir"]
            state = self.app.state_map.get(path_str, "UNSELECTED")
            node.set_label(self.format_label(Path(path_str).name, is_dir, state))
        for child in node.children:
            self.sync_tree_labels(child)

    def format_label(self, name: str, is_dir: bool, state: str) -> Text:
        icon = "📁" if is_dir else "📄"
        if state == "DETECTED":
            return Text.from_markup(f"[bold green]☑[/bold green] {icon} {name} [dim green](Auto-Detected)[/dim green]")
        elif state == "FALSE_POSITIVE":
            return Text.from_markup(f"[bold red]☐[/bold red] {icon} [strike]{name}[/strike] [dim red](False Positive)[/dim red]")
        elif state == "MANUAL":
            return Text.from_markup(f"[bold blue]☑[/bold blue] {icon} [bold]{name}[/bold] [dim blue](Manually Excluded)[/dim blue]")
        else:
            return Text.from_markup(f"[dim]☐[/dim] {icon} {name}")

    def load_directory(self, node) -> None:
        path = Path(node.data["path"])
        if node.children:
            return
            
        try:
            entries = sorted(list(os.scandir(path)), key=lambda e: (not e.is_dir(), e.name.lower()))
            for entry in entries:
                if entry.name in ('.git', '__pycache__'): 
                    continue
                    
                entry_path = str(Path(entry.path).resolve())
                is_dir = entry.is_dir()
                state = self.app.state_map.get(entry_path, "UNSELECTED")
                label = self.format_label(entry.name, is_dir, state)
                node.add(label, data={"path": entry_path, "is_dir": is_dir}, allow_expand=is_dir)
        except PermissionError:
            pass

    def on_tree_node_expanded(self, event: Tree.NodeExpanded) -> None:
        node = event.node
        if node.data and node.data.get("is_dir"):
            self.load_directory(node)

    def action_toggle_state(self) -> None:
        tree = self.query_one("#browse-tree", Tree)
        node = tree.cursor_node
        if not node or not node.data or node == tree.root:
            return

        path_str = node.data["path"]
        path_obj = Path(path_str)
        is_dir = node.data["is_dir"]
        current_state = self.app.state_map.get(path_str, "UNSELECTED")

        if current_state == "DETECTED":
            def set_fp(reason: str):
                self.app.state_map[path_str] = "FALSE_POSITIVE"
                self.app.reasons[path_str] = reason
                node.set_label(self.format_label(path_obj.name, is_dir, "FALSE_POSITIVE"))
                self.update_live_list()
            self.app.push_screen(ReasonModal(path_obj.name, "Flagging as False Positive"), set_fp)

        elif current_state == "FALSE_POSITIVE":
            self.app.state_map[path_str] = "DETECTED"
            node.set_label(self.format_label(path_obj.name, is_dir, "DETECTED"))
            self.update_live_list()

        elif current_state == "UNSELECTED":
            def set_manual(reason: str):
                self.app.state_map[path_str] = "MANUAL"
                self.app.reasons[path_str] = reason
                node.set_label(self.format_label(path_obj.name, is_dir, "MANUAL"))
                self.update_live_list()
            self.app.push_screen(ReasonModal(path_obj.name, "Manually Excluding Directory/File"), set_manual)

        elif current_state == "MANUAL":
            self.app.state_map[path_str] = "UNSELECTED"
            node.set_label(self.format_label(path_obj.name, is_dir, "UNSELECTED"))
            self.update_live_list()

    def update_live_list(self) -> None:
        detected, manual, false_pos = [], [], []

        for path_str, state in self.app.state_map.items():
            rel_path = str(Path(path_str).relative_to(self.app.project_root))
            if state == "DETECTED":
                detected.append(f"  [green]✓[/green] {rel_path}")
            elif state == "MANUAL":
                reason = self.app.reasons.get(path_str, "")
                reason_str = f" [dim]({reason})[/dim]" if reason else ""
                manual.append(f"  [blue]✓[/blue] {rel_path}{reason_str}")
            elif state == "FALSE_POSITIVE":
                reason = self.app.reasons.get(path_str, "No reason provided")
                false_pos.append(f"  [red]✗[/red] [strike]{rel_path}[/strike] [dim]({reason})[/dim]")

        lines = ["[bold underline]📋 Live Exclusion List Preview[/bold underline]\n"]
        if detected:
            lines.append("[bold green]Auto-Detected Tests (Will be excluded):[/bold green]")
            lines.extend(sorted(detected))
            lines.append("")
        if manual:
            lines.append("[bold blue]Manually Selected (Will be excluded):[/bold blue]")
            lines.extend(sorted(manual))
            lines.append("")
        if false_pos:
            lines.append("[bold red]Flagged False Positives (Will NOT be excluded):[/bold red]")
            lines.extend(sorted(false_pos))

        self.query_one("#live-list", Static).update("\n".join(lines))

    def action_back_screen(self) -> None:
        self.app.switch_screen("review")

    def action_confirm(self) -> None:
        self.app.finalize_and_exit()


# --- APP ORCHESTRATOR ---
class ExclusionTUI(App[dict]):
    CSS = """
    .screen-title {
        padding: 1 2;
        background: $boost;
        width: 100%;
    }
    """

    def __init__(self, findings: list[dict], project_root: str):
        super().__init__()
        self.project_root = Path(project_root).resolve().absolute()
        
        self.findings_map = {}
        for f in findings:
            abs_path = str(self.project_root.joinpath(f['file']).resolve().absolute())
            self.findings_map[abs_path] = f
            
        self.state_map = {path: "DETECTED" for path in self.findings_map.keys()}
        self.reasons = {}

    def on_mount(self) -> None:
        self.install_screen(ReviewScreen(), name="review")
        self.install_screen(BrowseScreen(), name="browse")
        self.push_screen("review")

    def finalize_and_exit(self) -> None:
        selected_for_exclusion = []
        false_positives = {}
        manual_exclusions = {} # THE FIX: Capture manual reasons

        for path_str, state in self.state_map.items():
            rel_path = str(Path(path_str).relative_to(self.project_root))
            if state in ("DETECTED", "MANUAL"):
                selected_for_exclusion.append(rel_path)
                if state == "MANUAL":
                    manual_exclusions[rel_path] = self.reasons.get(path_str, "")
            elif state == "FALSE_POSITIVE":
                false_positives[rel_path] = self.reasons.get(path_str, "")

        formatted_findings = {
            str(Path(abs_path).relative_to(self.project_root)): data 
            for abs_path, data in self.findings_map.items()
        }

        self.exit({
            "selected_for_exclusion": selected_for_exclusion,
            "false_positives": false_positives,
            "manual_exclusions": manual_exclusions,
            "original_findings": formatted_findings
        })


def generate_csv_report(tui_result: dict, output_path: str = "../REPORTS/testfinder_report.csv"):
    if not tui_result:
        return

    selected = set(tui_result["selected_for_exclusion"])
    false_positives = tui_result["false_positives"]
    manual_exclusions = tui_result.get("manual_exclusions", {})
    findings = tui_result["original_findings"]

    all_paths = set(selected) | set(false_positives.keys())
    REPORTS_DIR=Path("/".join(output_path.split("/")[:-1]))
    REPORTS_DIR=REPORTS_DIR.resolve()

    if not os.path.exists(REPORTS_DIR):
        print(f"Trying to create PATH {REPORTS_DIR}")
        os.mkdir(REPORTS_DIR)
    # 1. GENERATE CSV FOR HUMANS
    with open(output_path, mode='w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(["File/Folder Path", "Exclusion Status", "Test Hits", "Frameworks", "Initial Triggers", "User Comments"])

        for path in sorted(all_paths):
            data = findings.get(path, {})
            
            if path in false_positives:
                status = "False Positive (Skipped)"
                comments = false_positives.get(path, "")
            elif not data:
                status = "Manually Excluded"
                comments = manual_exclusions.get(path, "")
            else:
                status = "Auto-Detected Excluded"
                comments = ""

            hits = data.get('hit_count', 0) if data else "N/A"
            frameworks = " + ".join(data.get('frameworks', [])) if data else "N/A"
            triggers = " + ".join(data.get('reasons', [])) if data else "Manual Selection"

            writer.writerow([path, status, hits, frameworks, triggers, comments])
            
    # 2. GENERATE JSON FOR CI/CD PIPELINES (Copilot/LLM Validation)
    json_path = str(Path(output_path).with_suffix('.json'))
    pipeline_data = {
        "auto_detected_excluded": [p for p in selected if p not in manual_exclusions],
        "manually_excluded": [{"path": p, "reason": r} for p, r in manual_exclusions.items()],
        "flagged_false_positives": [{"path": p, "reason": r} for p, r in false_positives.items()]
    }
    
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(pipeline_data, f, indent=2)
    
    print(f"\n✅ Detailed exclusion report saved to {output_path}")
    print(f"✅ CI/CD validation data saved to {json_path}")