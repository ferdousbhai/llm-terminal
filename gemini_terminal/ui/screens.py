from textual import on
from textual.screen import ModalScreen
from textual.binding import Binding
from textual.containers import Horizontal, Container
from textual.widgets import Label, Input, Button, TextArea, LoadingIndicator
from textual.app import ComposeResult

from gemini_terminal.data_models import ServerConfig, AppConfig

class SettingsScreen(ModalScreen):
    """Screen for configuring app settings"""

    BINDINGS = [
        Binding(key="escape", action="dismiss", description="Close"),
        Binding(key="ctrl+s", action="save", description="Save"),
    ]

    def __init__(self, config: AppConfig):
        super().__init__()
        self.config = config
        self.is_saving = False
        self.verification_result = None
        self.old_api_key = config.gemini_api_key

    def compose(self) -> ComposeResult:
        with Container(id="settings-modal"):
            yield Label("Settings", id="settings-title")
            with Container(id="settings-content"):
                yield Label("Gemini API Key:")
                yield Input(
                    value=self.config.gemini_api_key,
                    password=True,
                    id="api-key-input"
                )
                yield Label("Model:")
                yield Input(
                    value=self.config.model,
                    id="model-input"
                )
                yield Label("System Prompt:")
                yield TextArea(
                    self.config.system_prompt,
                    id="system-prompt-input"
                )
                yield LoadingIndicator(id="settings-loading", classes="hide")
                yield Label("", id="settings-message")
            with Horizontal(id="settings-buttons"):
                yield Button("Cancel", id="settings-cancel", variant="error")
                yield Button("Save", id="settings-save", variant="success")

    @on(Button.Pressed, "#settings-cancel")
    def on_cancel(self) -> None:
        self.dismiss()
    
    @on(Button.Pressed, "#settings-save")
    async def on_save(self) -> None:
        if self.is_saving:
            return
            
        # Update config values
        api_key = self.query_one("#api-key-input", Input).value
        model = self.query_one("#model-input", Input).value
        system_prompt = self.query_one("#system-prompt-input", TextArea).text
        
        # Set loading state
        self.is_saving = True
        loading = self.query_one("#settings-loading", LoadingIndicator)
        loading.remove_class("hide")
        message = self.query_one("#settings-message", Label)
        message.update("Saving settings...")
        
        # Save new values to config
        self.config.gemini_api_key = api_key
        self.config.model = model
        self.config.system_prompt = system_prompt
        self.app.save_config()
        
        # Initialize Gemini with new settings
        self.app.initialize_gemini()
        
        # If API key changed, verify it works
        if api_key and (api_key != self.old_api_key or not self.old_api_key):
            message.update("Verifying API key...")
            success, result_message = await self.app.verify_api_key()
            self.verification_result = success
            
            if success:
                message.update(f"✅ {result_message}")
                message.add_class("success")
                message.remove_class("error")
                # Close screen after successful verification
                self.app.set_timer(2, self.dismiss)
            else:
                message.update(f"❌ {result_message}")
                message.add_class("error")
                message.remove_class("success")
                # Keep screen open if verification failed
        else:
            # No API key change, just close
            message.update("Settings saved")
            message.add_class("success")
            message.remove_class("error")
            self.app.set_timer(1, self.dismiss)
        
        # Reset state
        loading.add_class("hide")
        self.is_saving = False
    
    def action_save(self) -> None:
        self.app.call_later(self.on_save)

class ServerScreen(ModalScreen):
    """Screen for adding/editing MCP servers"""
    
    BINDINGS = [
        Binding(key="escape", action="dismiss", description="Close"),
        Binding(key="ctrl+s", action="save", description="Save"),
    ]
    
    def __init__(self, servers: list[ServerConfig], edit_server: ServerConfig | None = None):
        super().__init__()
        self.servers = servers
        self.edit_server = edit_server
        self.is_edit = edit_server is not None
        
    def compose(self) -> None:
        with Container(id="server-modal"):
            title = "Edit Server" if self.is_edit else "Add Server"
            yield Label(title, id="server-title")
            with Container(id="server-content"):
                yield Label("Server Name:")
                yield Input(
                    value=self.edit_server.name if self.is_edit else "",
                    id="server-name-input"
                )
                yield Label("Command:")
                yield Input(
                    value=self.edit_server.command if self.is_edit else "",
                    id="server-command-input"
                )
                yield Label("Arguments (one per line):")
                args_text = "\n".join(self.edit_server.args) if self.is_edit else ""
                yield TextArea(args_text, id="server-args-input")
                yield Label("Environment Variables (KEY=VALUE, one per line):")
                env_text = "\n".join([f"{k}={v}" for k, v in self.edit_server.env.items()]) if self.is_edit else ""
                yield TextArea(env_text, id="server-env-input")
            with Horizontal(id="server-buttons"):
                yield Button("Cancel", id="server-cancel", variant="error")
                yield Button("Save", id="server-save", variant="success")
                if self.is_edit:
                    yield Button("Delete", id="server-delete", variant="warning")
                
    @on(Button.Pressed, "#server-cancel")
    def on_cancel(self) -> None:
        self.dismiss()
    
    @on(Button.Pressed, "#server-save")
    def on_save(self) -> None:
        name = self.query_one("#server-name-input", Input).value
        command = self.query_one("#server-command-input", Input).value
        args_text = self.query_one("#server-args-input", TextArea).text
        env_text = self.query_one("#server-env-input", TextArea).text
        
        if not name or not command:
            return  # Simple validation
            
        args = [arg.strip() for arg in args_text.split('\n') if arg.strip()]
        
        env = {}
        for line in env_text.split('\n'):
            if '=' in line and line.strip():
                key, value = line.strip().split('=', 1)
                env[key] = value
        
        server = ServerConfig(
            name=name,
            command=command,
            args=args,
            env=env,
            active=self.edit_server.active if self.is_edit else False
        )
        
        if self.is_edit:
            # Replace existing server
            for i, s in enumerate(self.servers):
                if s.name == self.edit_server.name:
                    self.servers[i] = server
                    break
        else:
            # Add new server
            self.servers.append(server)
            
        self.app.save_config()
        self.app.rebuild_server_buttons()
        self.dismiss()
        
    @on(Button.Pressed, "#server-delete")
    def on_delete(self) -> None:
        if self.is_edit:
            # Remove server
            self.servers[:] = [s for s in self.servers if s.name != self.edit_server.name]
            self.app.save_config()
            self.app.rebuild_server_buttons()
        self.dismiss()
    
    def action_save(self) -> None:
        self.on_save() 