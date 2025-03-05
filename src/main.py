import asyncio

import llm
from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client
from textual import on, work, events
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Markdown, Button, TextArea, Static
from textual.containers import VerticalScroll, Horizontal

from src.config import MCPConfig
from src.ui.config_dialog import ConfigDialog
from src.ui.model_dialog import ModelDialog

# System prompt is now defined in MCPConfig

class Prompt(Markdown):
    pass

class Response(Markdown):
    BORDER_TITLE = "TERMINAL"

class ToolCall(Markdown):
    BORDER_TITLE = "Tool Call"

class MCPStatus(Static):
    """Show MCP connection status"""

class ChatInput(TextArea):
    """A custom TextArea for chat input that handles Enter and Shift+Enter properly."""

    # Define bindings for both Shift+Enter and alternative Mac-compatible key combinations
    BINDINGS = [
        ("shift+enter", "send_message", "Send Message"),
        # Add alternative key bindings that might work better on Mac
        ("ctrl+enter", "send_message", "Send Message"),
        ("meta+enter", "send_message", "Send Message"),  # Command+Enter on Mac
    ]
    
    def _on_key(self, event: events.Key) -> None:
        # Log the actual key being pressed to diagnose the issue
        app = self.app
        if isinstance(app, TerminalApp):
            # Uncomment this for debugging
            # app.notify(f"Raw key: {event.key}", timeout=1)
            pass
            
        # Handle multiple key combinations to send messages (adapt for Mac)
        if event.key in ["shift+enter", "ctrl+enter", "meta+enter"]:
            app = self.app
            if isinstance(app, TerminalApp):
                user_input = self.text.strip()
                if user_input:
                    self.clear()
                    asyncio.create_task(app._process_message_async(user_input))
                
                # Prevent default behavior
                event.prevent_default()
                event.stop()
                return
        
        # For all other keys, use default behavior
        super()._on_key(event)
    
    def action_send_message(self) -> None:
        """Action to send the current message from the chat input."""
        app = self.app
        if isinstance(app, TerminalApp):
            user_input = self.text.strip()
            if user_input:
                self.clear()
                asyncio.create_task(app._process_message_async(user_input))

class TerminalApp(App):
    AUTO_FOCUS = "#chat-input"

    CSS = """
    #system-prompt {
        height: 4;
        margin: 1;
        border: solid $primary;
    }

    #chat-input {
        height: 6;
        margin: 1 0 0 1;
        border: solid $primary;
        width: 90%;
    }
    
    #input-container {
        height: 6;
        margin: 0;
        padding: 0;
    }
    
    #send-button {
        margin: 1 1 0 0;
        width: 10%;
        height: 6;
    }

    #controls {
        height: 3;
        margin: 0 1;
    }

    Prompt {
        background: $primary 10%;
        color: $text;
        margin: 1;
        margin-right: 8;
        padding: 1 2 0 2;
    }

    Response {
        border: wide $success;
        background: $success 10%;
        color: $text;
        margin: 1;
        margin-left: 8;
        padding: 1 2 0 2;
    }

    ToolCall {
        border: wide $warning;
        background: $warning 10%;
        color: $text;
        margin: 1;
        padding: 1 2 0 2;
    }

    MCPStatus {
        width: 100%;
        background: $surface;
        color: $text-muted;
        padding: 0 1;
        text-align: right;
    }

    Notification {
        padding: 1 2;
        background: $primary;
        color: $text;
    }

    Notification.-error {
        background: $error;
    }

    Notification.-warning {
        background: $warning;
    }

    Notification.-success {
        background: $success;
    }

    .input-help {
        margin: 0 1 1 1;
        color: $text-muted;
        text-align: right;
        height: 1;
    }
    """

    # Add global bindings with Mac alternatives
    BINDINGS = [
        ("shift+enter", "send_message", "Send Message"),
        ("ctrl+enter", "send_message", "Send Message"),
        ("meta+enter", "send_message", "Send Message"),  # Command+Enter on Mac
        # Add a debug key binding to show key info
        ("f1", "show_key_info", "Display Key Info"),
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.session: ClientSession | None = None
        self.mcp_tools: list[types.Tool] = []
        self.mcp_connected = False
        self.config = MCPConfig.load()
        self.system_prompt = self.config.system_prompt
        self.is_initializing = True

    def compose(self) -> ComposeResult:
        yield Header()
        yield TextArea(self.system_prompt, id="system-prompt")
        with Horizontal(id="controls"):
            yield Button("New Conversation", id="new-conversation")
            yield Button("Connect MCP Server", id="connect-mcp")
            yield Button("Configure MCP", id="configure-mcp")
            yield Button("Select Model", id="select-model")
        yield MCPStatus("MCP: Not Connected")
        with VerticalScroll(id="chat-view"):
            yield Response("TERMINAL READY")
        with Horizontal(id="input-container"):
            yield ChatInput(id="chat-input", classes="chat-input")
            yield Button("Send", id="send-button", variant="primary")
        yield Static("Enter: new line | Shift+Enter or Ctrl+Enter or Click Send: send message", classes="input-help")
        yield Footer()

    def on_mount(self) -> None:
        try:
            # Try to use gpt-4.5-preview as the default model
            self.model = llm.get_model("gpt-4.5-preview")
        except Exception:
            # Fall back to system default if gpt-4.5-preview is not available
            self.model = llm.get_model()
        
        self.query_one("#system-prompt").load_text(self.system_prompt)
        self._update_model_status()
        
        # Configure text areas
        chat_input = self.query_one("#chat-input", ChatInput)
        chat_input.show_line_numbers = False
        self.query_one("#system-prompt", TextArea).show_line_numbers = False
        
        # Make sure the chat input is focused
        chat_input.focus()
        
        # Set to False after initialization is complete
        self.is_initializing = False

    @on(TextArea.Changed, "#system-prompt")
    def on_system_prompt_changed(self, event: TextArea.Changed) -> None:
        text_area = self.query_one("#system-prompt", TextArea)
        self.system_prompt = text_area.text
        
        # Save the updated system prompt to config
        self.config.system_prompt = self.system_prompt
        self.config.save()
        
        # Only show notification if not during initial app loading
        if not self.is_initializing:
            self.notify("System prompt updated and saved")

    @on(Button.Pressed, "#new-conversation")
    def on_new_conversation(self) -> None:
        chat_view = self.query_one("#chat-view")
        chat_view.remove_children()
        chat_view.mount(Response("TERMINAL READY"))
        self.notify("Started a new conversation")

    @on(Button.Pressed, "#connect-mcp")
    def on_connect_mcp(self) -> None:
        if not self.mcp_connected:
            self.connect_mcp_server()
        else:
            self.notify("Already connected to MCP server")

    @on(Button.Pressed, "#configure-mcp")
    async def show_config_dialog(self) -> None:
        dialog = ConfigDialog(self.config)
        result = await self.push_screen(dialog)
        if result:
            self.notify("MCP configuration saved")

    @on(Button.Pressed, "#select-model")
    async def show_model_dialog(self) -> None:
        dialog = ModelDialog()
        model_id = await self.push_screen(dialog)
        if model_id:
            self.model = llm.get_model(model_id)
            # Set this as the default model for future sessions
            try:
                import subprocess
                subprocess.run(["llm", "models", "default", model_id], check=True)
                self._update_model_status()
                self.notify(f"Switched to model: {model_id} and set as default")
            except Exception as e:
                self._update_model_status()
                self.notify(f"Switched to model: {model_id} (couldn't set as default: {str(e)})")

    @work(thread=True)
    def connect_mcp_server(self) -> None:
        # Ask for the server command and parameters
        # This could be improved with a proper dialog
        self.call_from_thread(self.notify, "Attempting to connect to MCP server...")

        # Run the async MCP connection in the thread
        asyncio.run(self._connect_mcp_async())

    async def _connect_mcp_async(self) -> None:
        try:
            server_params = StdioServerParameters(
                command=self.config.command,
                args=self.config.args if self.config.args is not None else [],
                env=self.config.env if self.config.env is not None else {}
            )

            async def handle_sampling_message(message: types.CreateMessageRequestParams) -> types.CreateMessageResult:
                prompt = message.messages[-1].content.text if message.messages else ""
                response = await asyncio.to_thread(
                    lambda: next(self.model.prompt(prompt, system=self.system_prompt))
                )

                return types.CreateMessageResult(
                    role="assistant",
                    content=types.TextContent(
                        type="text",
                        text=response,
                    ),
                    model="gpt-4o",
                    stopReason="endTurn",
                )

            self.transport = await stdio_client(server_params)
            read, write = self.transport

            self.session = ClientSession(read, write, sampling_callback=handle_sampling_message)
            await self.session.initialize()

            response = await self.session.list_tools()
            self.mcp_tools = response.tools

            self.mcp_connected = True

            tool_names = [tool.name for tool in self.mcp_tools]
            status_text = f"MCP: Connected - Available tools: {', '.join(tool_names)}"
            self.call_from_thread(self._update_mcp_status, status_text)
            self.call_from_thread(self.notify, f"Connected to MCP server with {len(self.mcp_tools)} tools")

        except Exception as e:
            self.call_from_thread(self.notify, f"Failed to connect to MCP server: {str(e)}", severity="error")

    def _update_mcp_status(self, text: str) -> None:
        status = self.query_one(MCPStatus)
        status.update(text)

    def _update_model_status(self) -> None:
        status = self.query_one(MCPStatus)
        model_name = self.model.model_id
        if self.mcp_connected:
            tool_names = [tool.name for tool in self.mcp_tools]
            status.update(f"Model: {model_name} | MCP: Connected - Available tools: {', '.join(tool_names)}")
        else:
            status.update(f"Model: {model_name} | MCP: Not Connected")

    def on_key(self, event: events.Key) -> None:
        """Global key handler for debugging."""
        # Uncomment this to debug specific key issues
        # if event.key in ["shift+enter", "ctrl+enter", "meta+enter", "enter"]:
        #     self.notify(f"Global key handler: {event.key}", timeout=2)
        pass

    async def _process_message_async(self, user_input: str) -> None:
        """Process a user message asynchronously."""
        chat_view = self.query_one("#chat-view")
        await chat_view.mount(Prompt(user_input))
        await chat_view.mount(response := Response())
        response.anchor()
        self.process_input(user_input, response)

    @work(thread=True)
    def process_input(self, prompt: str, response: Response) -> None:
        # If MCP is connected, check if we need to use tools based on user input
        need_tools = False
        if self.mcp_connected and self.mcp_tools:
            # Simple heuristic - check if the prompt mentions any tool by name
            # In a real implementation, you'd use the LLM to decide
            need_tools = any(tool.name.lower() in prompt.lower() for tool in self.mcp_tools)

        if need_tools:
            # Process with MCP tools
            self.process_with_mcp(prompt, response)
        else:
            # Regular LLM processing
            self.process_with_llm(prompt, response)

    def process_with_llm(self, prompt: str, response: Response) -> None:
        response_content = ""
        llm_response = self.model.prompt(prompt, system=self.system_prompt)
        for chunk in llm_response:
            response_content += chunk
            self.call_from_thread(response.update, response_content)

    @work(thread=True)
    def process_with_mcp(self, prompt: str, response: Response) -> None:
        # This would be more sophisticated in a real implementation
        # You'd typically have the LLM determine which tool to use
        chat_view = self.query_one("#chat-view")

        response_content = "Analyzing your request...\n"
        self.call_from_thread(response.update, response_content)

        # For demo purposes, we'll just use the first available tool
        if self.mcp_tools:
            tool = self.mcp_tools[0]
            tool_name = tool.name

            # Simple argument extraction
            # In practice, you'd use the LLM to determine arguments
            arguments = {"query": prompt}

            # Show the tool call in the UI
            tool_text = f"Calling tool: {tool_name}\nArguments: {arguments}"
            self.call_from_thread(chat_view.mount, ToolCall(tool_text))

            try:
                # Run the async MCP tool call
                result = asyncio.run(self._call_mcp_tool(tool_name, arguments))

                # Generate a response that incorporates the tool result
                result_text = "\n".join([content.text for content in result.content if hasattr(content, 'text')])
                final_prompt = f"{prompt}\n\nTool result: {result_text}"

                # Now use the LLM to generate a response that incorporates the tool result
                llm_response = self.model.prompt(
                    final_prompt,
                    system=f"{self.system_prompt}\nIncorporate the tool result into your response."
                )
                response_content = ""
                for chunk in llm_response:
                    response_content += chunk
                    self.call_from_thread(response.update, response_content)

            except Exception as e:
                error_msg = f"Error calling MCP tool: {str(e)}"
                self.call_from_thread(response.update, error_msg)
        else:
            self.call_from_thread(response.update, "No MCP tools available to handle your request.")

    async def _call_mcp_tool(self, tool_name: str, arguments: dict) -> types.CallToolResult:
        if not self.session:
            raise ValueError("MCP session not initialized")

        result = await self.session.call_tool(tool_name, arguments)
        return result

    @on(Button.Pressed, "#send-button")
    def on_send_button_pressed(self) -> None:
        """Handle the Send button being pressed."""
        chat_input = self.query_one("#chat-input", ChatInput)
        user_input = chat_input.text.strip()
        if user_input:
            chat_input.clear()
            asyncio.create_task(self._process_message_async(user_input))
            
    def action_send_message(self) -> None:
        """Send message from the chat input using keyboard shortcut."""
        chat_input = self.query_one("#chat-input", ChatInput)
        if chat_input:
            user_input = chat_input.text.strip()
            if user_input:
                chat_input.clear()
                asyncio.create_task(self._process_message_async(user_input))

    def action_show_key_info(self) -> None:
        """Display information about key bindings for debugging."""
        # Shows a notification with key binding info
        self.notify(
            "Key bindings: Shift+Enter, Ctrl+Enter, or Cmd+Enter to send messages.\n"
            "If Shift+Enter doesn't work, try the alternatives.",
            timeout=8
        )

if __name__ == "__main__":
    app = TerminalApp()
    app.run()