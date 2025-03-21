from textual.app import ComposeResult
from textual.widgets import Static


class MCPStatus(Static):
    """Show model information in the status bar."""

    DEFAULT_CSS = """
    MCPStatus {
        layout: horizontal;
        height: 1;
        padding: 0 1;
        background: $surface;
    }

    .status-text {
        width: 100%;
        color: $text-muted;
        text-align: right;
    }
    """

    def __init__(self):
        super().__init__("")

    def compose(self) -> ComposeResult:
        yield Static("", classes="status-text", id="status-text")

    def update_status(self, text: str = "") -> None:
        """Update the status text."""
        self.query_one("#status-text").update(text)