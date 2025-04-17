import logging
import os
import platform
import subprocess
from datetime import datetime
from logging import FileHandler
import sys

from textual import on, work
from textual.app import App, ComposeResult
from textual.widgets import Header, Input, Footer, Markdown, Button, Label
from textual.containers import VerticalScroll, Horizontal

from pydantic_ai import Agent
from pydantic_ai.exceptions import AgentRunError, UserError
from pydantic_ai.messages import (
    ModelResponse,
    TextPart,
    PartDeltaEvent,
    TextPartDelta,
    ToolCallPartDelta,
    PartStartEvent,
    ToolCallPart,
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    FinalResultEvent,
)
from pydantic_ai.mcp import MCPServerStdio

from .config import (
    MCP_CONFIG_PATH,
    SETTINGS_PATH,
    ensure_config_file,
    load_mcp_servers_from_config,
    load_settings,
    save_settings
)

class Prompt(Markdown):
    """Widget for user prompts"""
    pass

class Response(Markdown):
    """Widget for AI responses"""
    pass

class TerminalApp(App):
    """A terminal-based chat interface for PydanticAI with MCP integration"""
    AUTO_FOCUS = "Input"
    CSS = """
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

    #chat-view {  /* Ensure chat view takes available space */
        height: 1fr;
    }

    Horizontal { /* Ensure the button/input rows take minimal height */
        height: auto;
    }

    Label.label {
        margin: 1 1 1 2; /* T R B L */
        width: 15;
        text-align: right;
    }

    #system-prompt-input {
        width: 1fr;
    }

    #model-input {
        width: 1fr;
    }

    #config-buttons {
        height: auto;
        margin-top: 1;
        align: center middle;
    }
    """
    mcp_server_configs: dict[str, MCPServerStdio]
    agent: Agent | None = None

    def compose(self) -> ComposeResult:
        """Compose the UI layout"""
        yield Header()
        with Horizontal():
            yield Label("Model:", classes="label")
            yield Input(id="model-input", placeholder="Model (e.g., openai:gpt-4o)")
        with Horizontal():
            yield Label("System Prompt:", classes="label")
            yield Input(id="system-prompt-input", placeholder="Enter system prompt...")
        with Horizontal(id="config-buttons"):
            yield Button("Edit MCP Config", id="edit-config-button")
            yield Button("Reload MCP Config", id="reload-config-button")
        with VerticalScroll(id="chat-view"):
            yield Response(f"# {self.get_time_greeting()} How can I help?")
        with Horizontal():
            yield Button("New Chat", id="new-chat-button")
            yield Input(id="chat-input", placeholder="Ask me anything...")
        yield Footer()

    def get_time_greeting(self) -> str:
        """Return appropriate greeting based on time of day"""
        hour = datetime.now().hour
        if 5 <= hour < 12:
            return "Good morning!"
        elif 12 <= hour < 18:
            return "Good afternoon!"
        else:
            return "Good evening!"

    def on_mount(self) -> None:
        """Initialize the app, load configs, and settings."""
        ensure_config_file()
        self.mcp_server_configs = load_mcp_servers_from_config()
        logging.info(f"Loaded {len(self.mcp_server_configs)} MCP server configurations.")

        loaded_settings = load_settings()
        self.model_identifier = loaded_settings["model_identifier"]
        self.system_prompt = loaded_settings["system_prompt"]

        self.query_one("#model-input", Input).value = self.model_identifier
        self.query_one("#system-prompt-input", Input).value = self.system_prompt

        self.message_history = []

        self._initialize_agent()

        self.query_one("#chat-input", Input).focus()

    def _initialize_agent(self) -> None:
        """Initializes or re-initializes the Agent instance."""
        logging.info(f"Initializing agent with model '{self.model_identifier}' and {len(self.mcp_server_configs)} servers.")
        mcp_servers: list[MCPServerStdio] = list(self.mcp_server_configs.values())
        try:
            self.agent = Agent(
                self.model_identifier,
                system_prompt=self.system_prompt,
                mcp_servers=mcp_servers
            )
            logging.info("Agent initialized successfully.")
        except (UserError, AgentRunError) as e:
            logging.exception(f"Failed to initialize Agent with {self.model_identifier}: {e}")
            self.query_one("#chat-view").mount(Response(f"*Error initializing Agent: {e}. Please check model identifier and configuration.*"))
        except Exception as e:
            logging.exception(f"An unexpected error occurred during agent initialization: {e}")
            self.query_one("#chat-view").mount(Response(f"*Unexpected error initializing Agent: {e}.*"))

    @on(Input.Submitted, "#chat-input")
    async def on_input(self, event: Input.Submitted) -> None:
        """Handle input submissions, select servers, and run a dynamic agent."""
        chat_view = self.query_one("#chat-view")
        prompt = event.value
        event.input.clear()

        await chat_view.mount(Prompt(f"**You:** {prompt}"))
        await chat_view.mount(response := Response())
        response.anchor()

        self.process_prompt(prompt, response)

    @work(thread=True)
    async def process_prompt(self, prompt: str, response: Response) -> None:
        """Process the prompt: set up agent run and handle results."""
        logging.info(f"Processing prompt: {prompt}")
        initial_response_content = f"**{self.model_identifier}:** "
        self.call_from_thread(response.update, initial_response_content)

        if self.agent is None:
            logging.error("Agent is not initialized. Cannot process prompt.")
            error_message = f"{initial_response_content} -- **Error: Agent not initialized. Check configuration and logs.**"
            self.call_from_thread(response.update, error_message)
            return

        mcp_servers = list(self.mcp_server_configs.values())
        last_displayed_content = initial_response_content

        try:
            async with self.agent.run_mcp_servers():
                logging.info(f"MCP servers ({len(mcp_servers)}) started for agent.")
                async with self.agent.run_stream(prompt, message_history=self.message_history) as run_result:
                    logging.info("Agent stream started.")

                    last_displayed_content = await self._handle_stream_events(
                        run_result.stream(),
                        response,
                        initial_response_content
                    )

                    logging.info("Stream processing loop finished.")
                    self.message_history = run_result.all_messages()

                    try:
                        history_repr = repr(self.message_history)
                        logging.debug(f"Message history immediately after stream end ({len(self.message_history)} messages):\n{history_repr}")
                    except Exception as hist_log_e:
                        logging.error(f"Error logging message history representation: {hist_log_e}")

                    logging.info(f"Message history updated. Length: {len(self.message_history)}")

                    await self._finalize_response(response, last_displayed_content)

            logging.info(f"MCP servers ({len(mcp_servers)}) stopped for agent.")

        except Exception as e:
            logging.exception(f"Error during agent prompt processing: {e}")
            error_message = f"{last_displayed_content} -- **Error:** {e}"
            self.call_from_thread(response.update, error_message)

        logging.debug("Finished processing prompt with agent.")

    async def _handle_stream_events(self, stream, response: Response, initial_content: str) -> str:
        """Iterates through stream events, updates UI, and returns the last displayed content."""
        current_text_response = ""
        tool_call_in_progress_message = ""
        last_displayed_content = initial_content
        response_prefix = f"**{self.model_identifier}:** "

        async for event in stream:
            log_prefix = f"Stream Event Received: Type={type(event).__name__}"
            log_details = []

            content_to_display = last_displayed_content

            if isinstance(event, PartStartEvent):
                log_details.append(f"Index={event.index}")
                log_details.append(f"Part={event.part!r}")
                if isinstance(event.part, ToolCallPart):
                    tool_name = event.part.tool_name
                    tool_call_in_progress_message = f"\n*Assistant is using tool: `{tool_name}`...*"
                    content_to_display = f"{response_prefix}{current_text_response}{tool_call_in_progress_message}"
                    logging.info(f"Tool call started: {tool_name}")

            elif isinstance(event, PartDeltaEvent):
                log_details.append(f"Index={event.index}")
                if isinstance(event.delta, TextPartDelta):
                    log_details.append(f"Delta=TextPartDelta(content_delta={event.delta.content_delta!r})")
                    current_text_response += event.delta.content_delta
                    tool_call_in_progress_message = ""
                    content_to_display = f"{response_prefix}{current_text_response}"
                elif isinstance(event.delta, ToolCallPartDelta):
                    log_details.append(f"Delta=ToolCallPartDelta(args_delta={event.delta.args_delta})")
                    content_to_display = f"{response_prefix}{current_text_response}{tool_call_in_progress_message}"
                else:
                    log_details.append(f"Delta={event.delta!r}")

            elif isinstance(event, FunctionToolCallEvent):
                 log_details.append(f"Part={event.part!r}")

            elif isinstance(event, FunctionToolResultEvent):
                log_details.append(f"ToolCallID={event.tool_call_id!r}")
                log_details.append(f"Result={event.result!r}")

            elif isinstance(event, FinalResultEvent):
                if hasattr(event, 'tool_name'): log_details.append(f"ToolName={event.tool_name!r}")
                if hasattr(event, 'tool_call_id'): log_details.append(f"ToolCallID={event.tool_call_id!r}")
                if hasattr(event, 'data'): log_details.append(f"Data={event.data!r}")

            else:
                 log_details.append(f"EventRepr={event!r}")

            logging.debug(f"{log_prefix} | Details: {{ {', '.join(log_details)} }}")

            if content_to_display != last_displayed_content:
                self.call_from_thread(response.update, content_to_display)
                last_displayed_content = content_to_display

        return last_displayed_content

    async def _finalize_response(self, response: Response, last_displayed_content: str) -> None:
        """Extracts final text from history and updates UI if needed."""
        final_response_text = None
        try:
            for msg in reversed(self.message_history):
                if isinstance(msg, ModelResponse):
                    for part in msg.parts:
                        if isinstance(part, TextPart) and not hasattr(part, 'tool_call_id') and not hasattr(part, 'tool_return_id'):
                            final_response_text = part.content
                            break
                    if final_response_text is not None:
                        break

            if final_response_text:
                logging.info(f"Agent final response extracted from history: {final_response_text[:100]}...")
                final_expected_content = f"**{self.model_identifier}:** {final_response_text}"
                if final_expected_content != last_displayed_content:
                    logging.info("Stream ended before final text was fully displayed, performing final UI update.")
                    self.call_from_thread(response.update, final_expected_content)
                else:
                    logging.info("Final text response matches last streamed content.")
            else:
                logging.warning("Could not find final assistant text content in history after stream completion.")
        except Exception as log_e:
            logging.error(f"Error trying to extract/log final agent response from history: {log_e}")

    def _update_and_restart(self) -> None:
        """Save settings, reinitialize agent, and focus chat input."""
        if not save_settings(self.model_identifier, self.system_prompt):
            self.query_one("#chat-view").mount(Markdown(f"*Error saving settings to `{SETTINGS_PATH}`*"))
        self._initialize_agent()
        self.query_one("#chat-input", Input).focus()

    @on(Input.Submitted, "#model-input")
    @on(Input.Submitted, "#system-prompt-input")
    def on_settings_change_submitted(self, event: Input.Submitted) -> None:
        """Handle both model and system-prompt input submissions."""
        widget_id = event.input.id
        if widget_id == "model-input":
            new_model = event.value
            if new_model and new_model != self.model_identifier:
                self.model_identifier = new_model
                logging.info(f"Model identifier changed to: {self.model_identifier}")
                self.query_one("#chat-view").mount(Markdown(f"*Model set to **{self.model_identifier}**. Re-initializing agent...*"))
            elif not new_model:
                logging.warning("Model input submitted empty.")
                return
            else:
                logging.info("Model input submitted, but model identifier is unchanged.")
                return
        else:
            new_prompt = event.value
            if new_prompt and new_prompt != self.system_prompt:
                self.system_prompt = new_prompt
                logging.info(f"System prompt updated to: '{self.system_prompt[:50]}...'")
                self.query_one("#chat-view").mount(Markdown("*System prompt updated. Re-initializing agent...*"))
            else:
                logging.info("System prompt submitted, but prompt is unchanged.")
                return

        self._update_and_restart()

    @on(Button.Pressed)
    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Unified handler for new-chat, edit-config, and reload-config buttons."""
        btn_id = event.button.id
        if btn_id == "new-chat-button":
            logging.info("'New Chat' button pressed. Clearing history and display.")
            self.message_history = []
            chat_view = self.query_one("#chat-view")
            await chat_view.remove_children()
            await chat_view.mount(Response(f"# {self.get_time_greeting()} How can I help?"))
        elif btn_id == "edit-config-button":
            logging.info(f"Opening config file: {MCP_CONFIG_PATH}")
            self._open_file_in_editor(MCP_CONFIG_PATH)
        elif btn_id == "reload-config-button":
            logging.info("Reloading MCP configuration...")
            self.mcp_server_configs = load_mcp_servers_from_config()
            server_names = list(self.mcp_server_configs.keys())
            self._initialize_agent()
            self._log_to_chat(f"*MCP Configuration reloaded and agent re-initialized. Found {len(server_names)} server configs: {', '.join(server_names) or 'None'}*")
            logging.info(f"MCP configuration reloaded. Found configs: {server_names}")
        self._focus_input()

    def _log_to_chat(self, text: str) -> None:
        """Mount Markdown text to chat view."""
        self.query_one("#chat-view").mount(Markdown(text))

    def _focus_input(self) -> None:
        """Set focus back to the chat input."""
        self.query_one("#chat-input", Input).focus()

    def _open_file_in_editor(self, path: str) -> None:
        """Open a file in the default system editor, with error handling."""
        try:
            system = platform.system()
            if system == "Windows":
                os.startfile(path)
            elif system == "Darwin":
                subprocess.run(["open", path], check=True)
            else:
                subprocess.run(["xdg-open", path], check=True)
            self._log_to_chat(f"*Opened `{path}` for editing. Press 'Reload MCP Config' after saving.*")
        except FileNotFoundError:
            logging.error(f"Config file {path} not found.")
            self._log_to_chat(f"*Error: Config file `{path}` not found.*")
        except Exception as e:
            logging.error(f"Failed to open config file {path}: {e}")
            self._log_to_chat(f"*Error opening `{path}`: {e}*")

def main():
    """Synchronous entry point that sets up logging, runs initial async tasks, and starts the app."""
    log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(threadName)s - %(message)s')
    log_handler = FileHandler('app.log', mode='w')
    log_handler.setFormatter(log_formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    root_logger.addHandler(log_handler)

    try:
        logging.info("Starting Textual application.")
        app = TerminalApp()
        app.run()
        logging.info("Application finished.")

    except Exception as e:
        logging.basicConfig(filename='app.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(threadName)s - %(message)s')
        logging.exception("Application crashed.")
        print(f"Application crashed: {e}", file=sys.stderr)
        sys.exit(1)

# The if __name__ == "__main__": block is ommitted as we are using uv run to start the app
