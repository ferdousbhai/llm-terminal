from textual.widgets import Markdown, Button
from gemini_terminal.data_models import ServerConfig

class Prompt(Markdown):
    """Widget for user prompts"""
    pass


class Response(Markdown):
    """Widget for LLM responses"""
    BORDER_TITLE = "Gemini"


class ServerButton(Button):
    """Button representing a server that can be toggled"""
    def __init__(self, server: ServerConfig):
        super().__init__(server.name, id=f"server-{server.name}")
        self.server = server
        self.variant = "success" if server.active else "default"

    def toggle(self) -> None:
        self.server.active = not self.server.active
        self.variant = "success" if self.server.active else "default" 