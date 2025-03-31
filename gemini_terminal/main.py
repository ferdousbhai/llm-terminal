import os
import asyncio
from google.genai import types

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll, Container
from textual.widgets import (
    Header,
    Input,
    Footer,
    TextArea,
    Button,
)

from gemini_terminal.data_models import ServerConfig, AppConfig
from gemini_terminal.config import ConfigManager
from gemini_terminal.gemini_client import GeminiClient
from gemini_terminal.ui.components import Prompt, Response, ServerButton
from gemini_terminal.ui.screens import SettingsScreen, ServerScreen
from gemini_terminal.server.mcp_client import connect_to_server

class GeminiTerminalApp(App):
    """Gemini Terminal App with MCP integration"""
    
    TITLE = "Gemini Terminal"
    SUB_TITLE = "Powered by MCP & Textual"
    CSS_PATH = "gemini_terminal.tcss"
    BINDINGS = [
        Binding(key="ctrl+q", action="quit", description="Quit"),
        Binding(key="ctrl+s", action="show_settings", description="Settings"),
        Binding(key="ctrl+a", action="add_server", description="Add Server"),
    ]
    
    def __init__(self, config_path: str = "~/.gemini_terminal.yaml"):
        super().__init__()
        self.config_manager = ConfigManager(config_path)
        self.config = self.config_manager.load_config()
        self.active_servers = {}
        self.gemini_client = None
        self.initialize_gemini()
    
    def initialize_gemini(self) -> None:
        """Initialize the Gemini client with API key"""
        if self.config.gemini_api_key:
            self.gemini_client = GeminiClient(
                api_key=self.config.gemini_api_key,
                model=self.config.model
            )
    
    async def verify_api_key(self) -> tuple[bool, str]:
        """Verify the Gemini API key works
        
        Returns:
            Tuple of (success, message)
        """
        if not self.gemini_client:
            return False, "No API key configured"
            
        try:
            return await self.gemini_client.verify_api_key()
        except Exception as e:
            return False, f"Error verifying API key: {str(e)}"
    
    def save_config(self) -> None:
        """Save the current configuration"""
        self.config_manager.save_config(self.config)
    
    def compose(self) -> ComposeResult:
        """Compose the initial UI"""
        yield Header()
        
        with Container(id="app-container"):
            with VerticalScroll(id="chat-view"):
                yield Response("Hello! I'm Gemini. How can I help you?")
                
            with Container(id="input-container"):
                with Horizontal(id="input-row"):
                    yield Button("New", id="new-conversation-btn", variant="primary")
                    yield Input(placeholder="Ask me anything...", id="chat-input")
                
            with Container(id="servers-container"):
                with Horizontal(id="server-buttons"):
                    for server in self.config.servers:
                        yield ServerButton(server)
                
                with Horizontal(id="server-actions"):
                    yield Button("+ Add Server", id="add-server-btn")
        
        yield Footer()
        
    def on_mount(self) -> None:
        """Initialize the application when mounted"""
        # Nothing to do on mount
        pass
    
    def rebuild_server_buttons(self) -> None:
        """Rebuild the server buttons based on configuration"""
        server_buttons = self.query_one("#server-buttons")
        server_buttons.remove_children()
        
        for server in self.config.servers:
            server_buttons.mount(ServerButton(server))
    
    @on(Input.Submitted, "#chat-input")
    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle user input submission"""
        if not event.value.strip():
            return
            
        chat_input = self.query_one("#chat-input", Input)
        chat_view = self.query_one("#chat-view")
        
        # Display user prompt
        prompt_text = event.value
        await chat_view.mount(Prompt(prompt_text))
        
        # Clear input
        chat_input.value = ""
        
        # Create response widget
        response_widget = Response("...")
        await chat_view.mount(response_widget)
        response_widget.anchor()
        chat_view.scroll_end(animate=False)
        
        # Process message
        if not self.gemini_client:
            response_widget.update("Please set your Gemini API key in settings (Ctrl+S)")
            return
        
        # Check if any servers are active
        active_server_configs = [s for s in self.config.servers if s.active]
        
        if not active_server_configs:
            # No servers active, just use regular Gemini
            self.generate_response(prompt_text, response_widget)
        else:
            # Use MCP with active servers
            self.generate_mcp_response(prompt_text, active_server_configs, response_widget)
    
    @on(Button.Pressed, "#add-server-btn")
    def on_add_server_button(self) -> None:
        """Handle add server button press"""
        self.action_add_server()
        
    @on(Button.Pressed, "ServerButton")
    def on_server_toggle(self, event: Button.Pressed) -> None:
        """Handle server button toggle"""
        button = event.button
        if isinstance(button, ServerButton):
            button.toggle()
            self.save_config()
    
    @on(Button.Pressed, "#new-conversation-btn")
    async def on_new_conversation(self) -> None:
        """Handle new conversation button press"""
        chat_view = self.query_one("#chat-view")
        
        # Clear all messages
        chat_view.remove_children()
        
        # Add welcome message
        await chat_view.mount(Response("Hello! I'm Gemini. How can I help you?"))
        chat_view.scroll_end(animate=False)
    
    @work(thread=True)
    def generate_response(self, prompt: str, response_widget: Response) -> None:
        """Generate a response from Gemini without MCP"""
        def update_response(text: str):
            self.call_from_thread(response_widget.update, text)
            
        self.gemini_client.generate_content(
            system_prompt=self.config.system_prompt,
            user_prompt=prompt,
            on_chunk=update_response
        )
    
    @work
    async def generate_mcp_response(
        self, 
        prompt: str, 
        server_configs: list[ServerConfig], 
        response_widget: Response
    ) -> None:
        """Generate a response using Gemini with MCP integration"""
        # Update the UI to show processing
        await response_widget.update("Connecting to tools...")
        
        try:
            active_sessions = []
            all_tools = []
            
            # Connect to all active servers
            for server_config in server_configs:
                try:
                    server_data = await connect_to_server(server_config)
                    
                    # Convert MCP tools to Gemini Tool format
                    _, _, mcp_tools = server_data
                    server_tools = types.Tool(function_declarations=[
                        {
                            "name": tool.name,
                            "description": tool.description,
                            "parameters": tool.inputSchema,
                        }
                        for tool in mcp_tools
                    ])
                    
                    all_tools.append(server_tools)
                    active_sessions.append(server_data)
                except Exception as e:
                    await response_widget.update(f"Error connecting to {server_config.name}: {str(e)}")
                    return
            
            if not active_sessions:
                await response_widget.update("No active tool servers connected.")
                return
                
            # Use the Gemini client to generate a response with MCP
            await self.gemini_client.generate_mcp_content(
                system_prompt=self.config.system_prompt,
                user_prompt=prompt,
                mcp_sessions=active_sessions,
                mcp_tools=all_tools,
                on_update=response_widget.update
            )
            
        except Exception as e:
            error_message = f"Error: {str(e)}"
            await response_widget.update(error_message)
            
        finally:
            # Clean up sessions
            for _, session, _ in active_sessions:
                await session.close()
    
    def action_show_settings(self) -> None:
        """Show settings screen"""
        self.push_screen(SettingsScreen(self.config))
        
    def action_add_server(self) -> None:
        """Show add server screen"""
        self.push_screen(ServerScreen(self.config.servers))
    
    async def handle_server_button_press(self, button: Button) -> None:
        """Handle server button press to edit a server"""
        server_name = button.text
        for server in self.config.servers:
            if server.name == server_name:
                self.push_screen(ServerScreen(self.config.servers, server))
                break


def run():
    """Run the application"""
    app = GeminiTerminalApp()
    app.run()


if __name__ == "__main__":
    run() 