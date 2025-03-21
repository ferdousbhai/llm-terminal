from typing import ClassVar


from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, ListView, ListItem, Static


from src.config import AppConfig, ServerConfig


class ToolSettingsDialog(ModalScreen):
    BINDINGS: ClassVar[list[Binding]] = [
        Binding("escape", "cancel", "Cancel"),
    ]

    DEFAULT_CSS = """
    ToolSettingsDialog {
        align: center middle;
    }

    #dialog {
        padding: 1 2;
        width: 80;
        height: 40;
        border: thick $background 80%;
        background: $surface;
    }

    #server-list {
        height: 20;
        border: solid $primary;
        margin-bottom: 1;
    }

    #server-list-container {
        width: 100%;
        height: 22;
    }

    .server-item {
        height: 3;
        padding: 0 1;
        width: 100%;
    }

    .server-enabled {
        color: $success;
        border-left: thick $success;
    }

    .server-disabled {
        color: $text-muted;
        border-left: thick $error;
    }

    #add-server-form {
        height: 9;
        width: 100%;
    }

    .form-row {
        layout: horizontal;
        width: 100%;
        height: 3;
        margin-bottom: 1;
    }

    .form-label {
        width: 1fr;
        content-align: left middle;
    }

    .form-input {
        width: 4fr;
    }

    #buttons {
        layout: horizontal;
        width: 100%;
        height: 3;
        margin-top: 1;
    }

    #buttons Button {
        margin-right: 1;
    }
    """

    def __init__(self, config: AppConfig):
        super().__init__()
        self.config = config
        self.selected_server = None

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("MCP Server List")
            with Vertical(id="server-list-container"):
                yield ListView(id="server-list")

            yield Label("Add New Server")
            with Vertical(id="add-server-form"):
                with Horizontal(classes="form-row"):
                    yield Label("Server Name:", classes="form-label")
                    yield Input(id="server-name", placeholder="Local MCP Server", classes="form-input")
                with Horizontal(classes="form-row"):
                    yield Label("Command:", classes="form-label")
                    yield Input(id="server-command", placeholder="python", classes="form-input")
                with Horizontal(classes="form-row"):
                    yield Label("Arguments:", classes="form-label")
                    yield Input(id="server-args", placeholder="path/to/server.py,--arg1,--arg2", classes="form-input")

            with Horizontal(id="buttons"):
                yield Button("Add Server", variant="primary", id="add-server")
                yield Button("Remove Selected", variant="error", id="remove-server")
                yield Button("Toggle Selected", variant="warning", id="toggle-server")
                yield Button("Save & Close", variant="success", id="save")
                yield Button("Cancel", variant="default", id="cancel")

    def on_mount(self) -> None:
        self._refresh_server_list()

    def _refresh_server_list(self) -> None:
        """Refresh the server list display."""
        server_list = self.query_one("#server-list")
        server_list.clear()

        for i, server in enumerate(self.config.servers):
            status_text = "Enabled" if server.enabled else "Disabled"
            
            # Create the label first
            label = Static(
                f"{server.name} ({server.command} {' '.join(server.args)}) - {status_text}",
            )
            
            # Create the list item with the label as a child
            item = ListItem(
                label,
                id=f"server-{i}",
                classes="server-item"
            )
            
            # Add appropriate status class
            if server.enabled:
                item.add_class("server-enabled")
            else:
                item.add_class("server-disabled")
            
            # Add the item to the list
            server_list.append(item)

    @on(ListView.Selected)
    def handle_list_selection(self, event: ListView.Selected) -> None:
        """Handle server selection in the list using event binding."""
        item_id = event.item.id
        if item_id and item_id.startswith("server-"):
            self.selected_server = int(item_id.split("-")[1])
        else:
            self.selected_server = None

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        button_id = event.button.id
        
        if button_id == "add-server":
            name = self.query_one("#server-name").value.strip()
            command = self.query_one("#server-command").value.strip()
            args_text = self.query_one("#server-args").value
            args = [arg.strip() for arg in args_text.split(",") if arg.strip()]
            
            if command:
                # If no name was provided, generate one from the command
                name_auto_generated = False
                if not name:
                    base_name = command.split("/")[-1]  # Get the last part of the path
                    name = f"{base_name} Server"
                    name_auto_generated = True
                
                new_server = ServerConfig(
                    name=name,
                    command=command,
                    args=args,
                    enabled=True
                )
                self.config.servers.append(new_server)
                self._refresh_server_list()
                
                # Clear form inputs
                self.query_one("#server-name").value = ""
                self.query_one("#server-command").value = ""
                self.query_one("#server-args").value = ""
                
                # Show notification if name was auto-generated
                if name_auto_generated:
                    self.notify(f"Server name auto-generated as '{name}'")
            else:
                # Show error notification
                self.notify("Command is required to add a server", severity="error")
        
        elif button_id == "remove-server" and self.selected_server is not None:
            if 0 <= self.selected_server < len(self.config.servers):
                self.config.servers.pop(self.selected_server)
                self.selected_server = None
                self._refresh_server_list()
        
        elif button_id == "toggle-server" and self.selected_server is not None:
            if 0 <= self.selected_server < len(self.config.servers):
                server = self.config.servers[self.selected_server]
                server.enabled = not server.enabled
                self._refresh_server_list()
        
        elif button_id == "save":
            # Save configuration
            self.config.save()
            self.dismiss(True)
        
        elif button_id == "cancel":
            self.dismiss(False)

    # Action to cancel dialog with Escape key
    action_cancel = lambda self: self.dismiss(False) 