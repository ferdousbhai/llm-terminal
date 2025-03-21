import asyncio
import subprocess
from contextlib import AsyncExitStack
from pathlib import Path
from typing import ClassVar

import llm
from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client
from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Button, Footer, Header, Markdown, TextArea

from src.config import AppConfig
from src.ui.model_dialog import ModelDialog
from src.ui.server_toggles import ServerToggle, ServerToggleBar
from src.ui.status import MCPStatus
from src.ui.tool_settings import ToolSettingsDialog

DEFAULT_MODEL = "gpt-4.5-preview"

class Prompt(Markdown):
    pass

class Response(Markdown):
    BORDER_TITLE = "TERMINAL"

class ToolCall(Markdown):
    BORDER_TITLE = "Tool Call"

class TerminalApp(App):
    AUTO_FOCUS = "#chat-input"
    CSS_PATH = Path(__file__).parent / "ui" / "styles.css"
    BINDINGS: ClassVar[list[tuple[str, str, str]]] = [
        ("f1", "show_key_info", "Display Key Info")
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.session = None
        self.mcp_tools = []
        self.mcp_connected = False
        self.config = AppConfig.load()
        self.system_prompt = self.config.system_prompt
        self.is_initializing = True
        self.exit_stack = None
        self.model = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield TextArea(self.system_prompt, id="system-prompt")
        with Horizontal(id="controls"):
            yield Button("New Conversation", id="new-conversation")
            yield Button("Tool Settings", id="tool-settings")
            yield Button("Select Model", id="select-model")
        yield MCPStatus()
        with VerticalScroll(id="chat-view"):
            yield Response("TERMINAL READY")
        with Horizontal(id="input-container"):
            yield TextArea(id="chat-input", classes="chat-input")
            yield Button("Send", id="send-button", variant="primary")
        yield ServerToggleBar()
        yield Footer()

    def on_mount(self) -> None:
        try:
            self.model = llm.get_model(DEFAULT_MODEL)
        except Exception:
            self.model = llm.get_model()

        # Configure UI elements
        self.query_one("#system-prompt").load_text(self.system_prompt)
        self._update_status()

        for text_area in self.query(TextArea):
            text_area.show_line_numbers = False

        # Initialize server toggle bar
        self.query_one(ServerToggleBar).update_servers(self.config.servers)
        self.query_one("#chat-input").focus()
        self.is_initializing = False

    def _update_status(self) -> None:
        self.query_one(MCPStatus).update_status(f"Model: {self.model.model_id}")

    @on(TextArea.Changed, "#system-prompt")
    def on_system_prompt_changed(self, _: TextArea.Changed) -> None:
        self.system_prompt = self.query_one("#system-prompt").text
        self.config.system_prompt = self.system_prompt
        self.config.save()

        if not self.is_initializing:
            self.notify("System prompt updated and saved")

    @on(Button.Pressed, "#new-conversation")
    def on_new_conversation(self) -> None:
        chat_view = self.query_one("#chat-view")
        chat_view.remove_children()
        chat_view.mount(Response("TERMINAL READY"))
        self.notify("Started a new conversation")

    @on(Button.Pressed, "#tool-settings")
    async def show_tool_settings(self) -> None:
        if await self.push_screen(ToolSettingsDialog(self.config)):
            self.notify("Tool settings saved")
            self.query_one(ServerToggleBar).update_servers(self.config.servers)

    @on(Button.Pressed, "#select-model")
    async def show_model_dialog(self) -> None:
        if model_id := await self.push_screen(ModelDialog()):
            self.model = llm.get_model(model_id)
            try:
                subprocess.run(["llm", "models", "default", model_id], check=True)
                msg = f"Switched to model: {model_id} and set as default"
            except Exception as e:
                msg = (
                    f"Switched to model: {model_id} "
                    f"(couldn't set as default: {format(e)})"
                )
            self._update_status()
            self.notify(msg)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if not isinstance(event.button, ServerToggle):
            return

        server_index = event.button.server_index
        if 0 <= server_index < len(self.config.servers):
            if event.button.is_connected:
                event.button.is_connected = False
                self.disconnect_mcp_server(server_index)
            else:
                self.connect_mcp_server(server_index)

    def disconnect_mcp_server(self, server_index: int) -> None:
        if not self.session:
            return
        try:
            self.mcp_connected = self.session = None
            self.mcp_tools.clear()
            self._close_session_in_thread()
            self._update_status()
            server_name = self.config.servers[server_index].name
            self.notify(f"Disconnected from MCP server: {server_name}")
        except Exception as e:
            self.notify(f"Error during disconnection: {format(e)}", severity="error")

    @work(thread=True)
    def _close_session_in_thread(self) -> None:
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            if self.exit_stack:
                exit_stack, self.exit_stack = self.exit_stack, None
                loop.run_until_complete(exit_stack.aclose())

            loop.close()
        except Exception as e:
            self.call_from_thread(
                self.notify,
                f"Error closing session: {format(e)}",
                severity="warning"
            )

    @work(thread=True)
    def connect_mcp_server(self, server_index: int | None = None) -> None:
        if server_index is None:
            enabled_servers = (
                (i, s) for i, s in enumerate(self.config.servers) if s.enabled
            )
            server_index = next((i for i, _ in enabled_servers), None)

        if server_index is None or server_index >= len(self.config.servers):
            self.call_from_thread(
                self.notify,
                "No enabled MCP servers available",
                severity="warning"
            )
            return

        server = self.config.servers[server_index]
        self.call_from_thread(
            self.notify,
            f"Attempting to connect to MCP server: {server.name}...",
            severity="info"
        )

        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._connect_mcp_async(server_index))
            loop.close()
        except Exception as e:
            self.call_from_thread(
                self.notify,
                f"Failed to connect to MCP server: {format(e)}",
                severity="error"
            )

    async def _connect_mcp_async(self, server_index: int) -> None:
        try:
            server = self.config.servers[server_index]
            server_params = StdioServerParameters(
                command=server.command,
                args=server.args or [],
                env=server.env or {}
            )

            async def handle_sampling_message(
                message: types.CreateMessageRequestParams
            ) -> types.CreateMessageResult:
                prompt = message.messages[-1].content.text if message.messages else ""
                response = await asyncio.to_thread(
                    lambda: next(self.model.prompt(prompt, system=self.system_prompt))
                )
                return types.CreateMessageResult(
                    role="assistant",
                    content=types.TextContent(type="text", text=response),
                    model="gpt-4o",
                    stopReason="endTurn",
                )

            self.exit_stack = AsyncExitStack()
            transport_ctx = stdio_client(server_params)
            stdio_transport = await self.exit_stack.enter_async_context(transport_ctx)
            self.session = await self.exit_stack.enter_async_context(
                ClientSession(
                    *stdio_transport,
                    sampling_callback=handle_sampling_message
                )
            )

            response = await self.session.list_tools()
            self.mcp_tools = response.tools
            self.mcp_connected = True

            self.call_from_thread(self._update_status)
            self.call_from_thread(
                self.query_one(ServerToggleBar).set_connected,
                server_index,
                True
            )
            self.call_from_thread(
                self.notify,
                (f"Connected to MCP server {server.name} with "
                 f"{len(self.mcp_tools)} tools: "
                 f"{', '.join(t.name for t in self.mcp_tools)}"),
                severity="success"
            )

        except Exception as e:
            import traceback
            self.call_from_thread(
                self.notify, 
                f"Failed to connect to MCP server: {e}\n{traceback.format_exc()}", 
                severity="error"
            )
            if self.exit_stack:
                await self.exit_stack.aclose()
                self.exit_stack = None

    async def _process_message_async(self, user_input: str) -> None:
        chat_view = self.query_one("#chat-view")
        await chat_view.mount(Prompt(user_input))
        await chat_view.mount(response := Response())
        response.anchor()
        self.process_input(user_input, response)

    @work(thread=True)
    def process_input(self, prompt: str, response: Response) -> None:
        need_tools = self.mcp_connected and self.mcp_tools and any(
            tool.name.lower() in prompt.lower() for tool in self.mcp_tools
        )

        if need_tools:
            self.process_with_mcp(prompt, response)
        else:
            self.process_with_llm(prompt, response)

    def process_with_llm(self, prompt: str, response: Response) -> None:
        for chunk in self.model.prompt(prompt, system=self.system_prompt):
            self.call_from_thread(response.update, chunk)

    @work(thread=True)
    def process_with_mcp(self, prompt: str, response: Response) -> None:
        if not self.mcp_tools:
            self.call_from_thread(response.update, "No MCP tools available.")
            return

        self.query_one("#chat-view")
        tool = self.mcp_tools[0]
        arguments = {"query": prompt}

        try:
            loop = asyncio.new_event_loop()
            result = loop.run_until_complete(self._call_mcp_tool(tool.name, arguments))
            result_text = "\n".join([
                c.text for c in result.content if hasattr(c, 'text')
            ])
            final_prompt = f"{prompt}\n\nTool result: {result_text}"

            for chunk in self.model.prompt(
                final_prompt,
                system=f"{self.system_prompt}\nIncorporate the tool result."
            ):
                self.call_from_thread(response.update, chunk)
        except Exception as e:
            self.call_from_thread(response.update, f"Error: {format(e)}")
        finally:
            loop.close()

    async def _call_mcp_tool(
        self, tool_name: str, arguments: dict
    ) -> types.CallToolResult:
        if not self.session:
            raise ValueError("MCP session not initialized")
        return await self.session.call_tool(tool_name, arguments)

    @on(Button.Pressed, "#send-button")
    def on_send_button_pressed(self) -> None:
        chat_input = self.query_one("#chat-input", TextArea)
        if user_input := chat_input.text.strip():
            chat_input.clear()
            task = self._process_message_async(user_input)
            self._message_task = asyncio.create_task(task)

    def action_show_key_info(self) -> None:
        self.notify(
            "Using standard TextArea behavior with Send button for submissions.",
            timeout=5
        )

if __name__ == "__main__":
    app = TerminalApp()
    app.run()