from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label
from textual.binding import Binding
from src.config import MCPConfig

class ConfigDialog(ModalScreen):
    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    DEFAULT_CSS = """
    ConfigDialog {
        align: center middle;
    }

    #dialog {
        grid-size: 2;
        grid-gutter: 1 2;
        grid-rows: 4;
        padding: 1 2;
        width: 60;
        height: auto;
        border: thick $background 80%;
        background: $surface;
    }

    #dialog Button {
        width: 100%;
    }

    #dialog #buttons {
        column-span: 2;
        height: 3;
        align-horizontal: right;
        padding-right: 1;
    }
    """

    def __init__(self, config: MCPConfig):
        super().__init__()
        self.config = config

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("Command:")
            yield Input(
                value=self.config.command,
                id="command",
                placeholder="python"
            )
            yield Label("Arguments (comma-separated):")
            yield Input(
                value=",".join(self.config.args) if self.config.args else "",
                id="args",
                placeholder="path/to/server.py,--arg1,--arg2"
            )
            with Vertical(id="buttons"):
                yield Button("Save", variant="primary", id="save")
                yield Button("Cancel", variant="default", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save":
            command = self.query_one("#command").value
            args = [arg.strip() for arg in self.query_one("#args").value.split(",") if arg.strip()]

            self.config.command = command
            self.config.args = args
            self.config.save()

            self.dismiss(True)
        else:
            self.dismiss(False)

    def action_cancel(self) -> None:
        self.dismiss(False)