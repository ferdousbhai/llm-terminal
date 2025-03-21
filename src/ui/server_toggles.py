from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.reactive import reactive
from textual.widgets import Button, Static

class ServerToggle(Button):
    """Toggle button for MCP servers."""

    is_connected = reactive(False)

    DEFAULT_CSS = """
    ServerToggle {
        min-width: 20;
        height: 3;
        margin: 0 1 0 0;
    }
    
    ServerToggle.-connected {
        background: $success;
    }
    """
    
    def __init__(self, server_name: str, server_index: int):
        super().__init__(f"{server_name}")
        self.server_index = server_index
    
    def watch_is_connected(self, connected: bool) -> None:
        if connected:
            self.add_class("-connected")
        else:
            self.remove_class("-connected")


class ServerToggleBar(Horizontal):
    """Container for server toggle buttons."""
    
    DEFAULT_CSS = """
    ServerToggleBar {
        width: 100%;
        height: auto;
        margin: 0 1 1 1;
        background: $surface;
    }
    
    ServerToggleBar .server-label {
        margin-right: 1;
        content-align: center middle;
        width: auto;
        min-width: 10;
    }
    """
    
    def __init__(self):
        super().__init__(id="server-toggle-bar")
        self.toggles = []
    
    def compose(self) -> ComposeResult:
        yield Static("MCP Servers:", classes="server-label")
    
    def update_servers(self, servers) -> None:
        """Update the server toggle buttons based on config."""
        # Remove old toggles
        for toggle in self.toggles:
            toggle.remove()
        
        self.toggles = []
        
        # Add toggles for each enabled server
        for i, server in enumerate(servers):
            if server.enabled:
                toggle = ServerToggle(server.name, i)
                self.mount(toggle)
                self.toggles.append(toggle)
        
        # Hide bar if no servers are available
        if not self.toggles:
            self.styles.display = "none"
        else:
            self.styles.display = "block"
    
    def set_connected(self, server_index: int, is_connected: bool) -> None:
        """Set the connected state for a specific server toggle."""
        for toggle in self.toggles:
            if toggle.server_index == server_index:
                toggle.is_connected = is_connected
                break 