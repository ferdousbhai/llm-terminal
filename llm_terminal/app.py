import json
import logging
import os
import platform
import subprocess
from datetime import datetime

from textual import on, work
from textual.app import App, ComposeResult
from textual.widgets import Header, Input, Footer, Markdown, Button, Label
from textual.containers import VerticalScroll, Horizontal

from pydantic_ai import Agent
from pydantic_ai.mcp import MCPServerStdio

# Define a system prompt
SYSTEM = """You are a helpful AI assistant."""
CONFIG_PATH = "mcp_config.json"
DEFAULT_CONFIG = {
    "mcpServers": {
        "run_python": {
            "command": "deno",
            "args": [
                "run",
                "-N",
                "-R=node_modules",
                "-W=node_modules",
                "--node-modules-dir=auto",
                "jsr:@pydantic/mcp-run-python",
                "stdio",
            ]
        }
    }
}

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

    def ensure_config_file(self, path: str = CONFIG_PATH) -> None:
        """Creates the default config file if it doesn't exist."""
        if not os.path.exists(path):
            logging.info(f"Configuration file not found at {path}. Creating default.")
            try:
                with open(path, 'w') as f:
                    json.dump(DEFAULT_CONFIG, f, indent=2)
                logging.info(f"Default configuration file created at {path}.")
            except Exception as e:
                logging.error(f"Failed to create default configuration file at {path}: {e}")

    def load_mcp_servers_from_config(self, path: str = CONFIG_PATH) -> list[MCPServerStdio]:
        """Loads MCP server configurations from the JSON file."""
        servers = []
        try:
            with open(path, 'r') as f:
                config_data = json.load(f)

            mcp_servers_config = config_data.get("mcpServers", {})
            if not mcp_servers_config:
                logging.warning(f"No 'mcpServers' found or empty in {path}. No servers loaded.")
                return []

            for server_name, server_details in mcp_servers_config.items():
                command = server_details.get("command")
                args = server_details.get("args")
                env = server_details.get("env")
                if command and isinstance(args, list):
                    log_msg = f"Loading MCP server '{server_name}' with command '{command}', args {args}"
                    if env is not None:
                         log_msg += f", and env {env}"
                    logging.info(log_msg)
                    servers.append(MCPServerStdio(command, args=args, env=env))
                else:
                    logging.warning(f"Skipping invalid config for server '{server_name}' in {path}.")

        except FileNotFoundError:
            logging.error(f"Configuration file not found at {path}. Cannot load servers.")
            self.ensure_config_file(path)
            return self.load_mcp_servers_from_config(path) # Try loading again
        except json.JSONDecodeError as e:
            logging.error(f"Error decoding JSON from {path}: {e}.")
            self.query_one("#chat-view").mount(Markdown(f"*Error loading MCP config: Invalid JSON in {path}*"))
        except Exception as e:
            logging.error(f"An unexpected error occurred while loading configuration from {path}: {e}")
            self.query_one("#chat-view").mount(Markdown(f"*Error loading MCP config: {e}*"))

        return servers

    def on_mount(self) -> None:
        """Initialize the agent and MCP server on app mount"""
        self.ensure_config_file()
        self.servers = self.load_mcp_servers_from_config()
        self.model_identifier = "openai:gpt-4o"
        self.system_prompt = SYSTEM
        self.query_one("#model-input", Input).value = self.model_identifier
        self.query_one("#system-prompt-input", Input).value = self.system_prompt
        self.initialize_agent()
        self.message_history = []
        self.query_one("#chat-input", Input).focus()

    def initialize_agent(self) -> None:
        """Initializes or re-initializes the agent."""
        server_count = len(self.servers)
        logging.info(f"Initializing agent with model: {self.model_identifier}, {server_count} MCP servers, prompt: '{self.system_prompt[:50]}...'")
        try:
            self.agent = Agent(self.model_identifier, system_prompt=self.system_prompt, mcp_servers=self.servers)
            logging.info("Agent initialized successfully.")
        except Exception as e:
            logging.error(f"Failed to initialize agent with {self.model_identifier}: {e}")
            self.query_one("#chat-view").mount(Markdown(f"*Error initializing Agent: {e}*"))
            self.agent = None # Agent is not usable

    @on(Input.Submitted, "#chat-input")
    async def on_input(self, event: Input.Submitted) -> None:
        """Handle input submissions."""
        if not self.agent:
            self.query_one("#chat-view").mount(Response("*Agent not initialized. Please check configuration and reload.*"))
            return

        chat_view = self.query_one("#chat-view")
        prompt = event.value
        event.input.clear()

        await chat_view.mount(Prompt(f"**You:** {prompt}"))

        await chat_view.mount(response := Response())
        response.anchor()

        self.process_prompt(prompt, response)
        logging.info(f"Input submitted: {prompt}")

    @work(thread=True)
    async def process_prompt(self, prompt: str, response: Response) -> None:
        """Process the prompt with the agent and update the response"""
        if not self.agent:
            self.call_from_thread(response.update, "**Error:** Agent not initialized.")
            return

        logging.info(f"Processing prompt: {prompt}")
        response_content = f"**{self.model_identifier}:** "
        self.call_from_thread(response.update, response_content)

        try:
            async with self.agent.run_mcp_servers():
                logging.info("MCP servers started.")
                async with self.agent.run_stream(prompt, message_history=self.message_history) as run_result:
                    logging.info("Agent stream started.")
                    async for accumulated_chunk in run_result.stream():
                        response_content = f"**{self.model_identifier}:** {accumulated_chunk}"
                        self.call_from_thread(response.update, response_content)

                    self.message_history = run_result.all_messages()
                    logging.info(f"Message history updated. Length: {len(self.message_history)}")

                    # Log the final response from the agent
                    final_response_text = None
                    try:
                        for msg in reversed(self.message_history):
                            # Check if it's a ModelResponse likely containing the final text
                            if hasattr(msg, 'kind') and msg.kind == 'response' and hasattr(msg, 'parts'):
                                for part in msg.parts:
                                    # Find a part with content that isn't a known non-text type (like ToolCallPart)
                                    # Heuristic: check for 'content' and lack of 'tool_call_id'
                                    if hasattr(part, 'content') and not hasattr(part, 'tool_call_id'):
                                        final_response_text = part.content
                                        break # Found the text part
                                if final_response_text is not None:
                                    break # Found the text in the latest relevant message

                        if final_response_text:
                            logging.info(f"Agent final response: {final_response_text}")
                        else:
                            logging.warning("Could not find assistant text content in final history.")
                    except Exception as log_e:
                        logging.error(f"Error trying to log final agent response: {log_e}")

            logging.info("MCP servers stopped.")
        except Exception as e:
            logging.exception(f"Error during prompt processing: {e}")
            # Pass error message without newline characters in the f-string directly
            error_message = f"{response_content} -- **Error:** {e}"
            self.call_from_thread(response.update, error_message)

        logging.debug("Finished processing prompt.")

    @on(Input.Submitted, "#model-input")
    def on_model_input_submitted(self, event: Input.Submitted) -> None:
        """Handle model input submission."""
        new_model_identifier = event.value
        if new_model_identifier and new_model_identifier != self.model_identifier:
            self.model_identifier = new_model_identifier
            # Corrected f-string: removed trailing backslash
            logging.info(f"Model identifier changed to: {self.model_identifier}")
            self.initialize_agent()
            if self.agent:
                self.query_one("#chat-view").mount(Markdown(f"*Model set to **{self.model_identifier}**.*"))
            self.query_one("#chat-input").focus()
        elif not new_model_identifier:
            logging.warning("Model input submitted empty.")
        else: # Re-add the previously deleted else block
            logging.info("Model input submitted, but model identifier is unchanged.")

    @on(Input.Submitted, "#system-prompt-input")
    def on_system_prompt_input_submitted(self, event: Input.Submitted) -> None:
        """Handle system prompt input submission."""
        new_prompt = event.value
        if new_prompt != self.system_prompt:
            self.system_prompt = new_prompt
            logging.info(f"System prompt updated to: '{self.system_prompt[:50]}...'")
            self.initialize_agent()
            if self.agent:
                self.query_one("#chat-view").mount(Markdown("*System prompt updated.*"))
            self.query_one("#chat-input").focus()
        else:
            logging.info("System prompt submitted, but prompt is unchanged.")

    @on(Button.Pressed, "#new-chat-button")
    async def on_new_chat_button_pressed(self, event: Button.Pressed) -> None:
        """Handle 'New Chat' button press."""
        logging.info("'New Chat' button pressed. Clearing history and display.")
        self.message_history = []

        chat_view = self.query_one("#chat-view")
        await chat_view.remove_children()

        await chat_view.mount(Response(f"# {self.get_time_greeting()} How can I help?"))

        self.query_one("#chat-input", Input).focus()

    @on(Button.Pressed, "#edit-config-button")
    def on_edit_config_button_pressed(self, event: Button.Pressed) -> None:
        """Open the MCP configuration file in the default editor."""
        logging.info(f"Attempting to open MCP config file: {CONFIG_PATH}")
        try:
            system = platform.system()
            if system == "Windows":
                os.startfile(CONFIG_PATH)
            elif system == "Darwin": # macOS
                subprocess.run(["open", CONFIG_PATH], check=True)
            else: # Linux and other UNIX-like
                subprocess.run(["xdg-open", CONFIG_PATH], check=True)
            logging.info(f"Opened {CONFIG_PATH} for editing.")
            self.query_one("#chat-view").mount(Markdown(f"*Opened `{CONFIG_PATH}` for editing. Press 'Reload MCP Config' after saving.*"))
        except FileNotFoundError:
             logging.error(f"Config file {CONFIG_PATH} not found.")
             self.query_one("#chat-view").mount(Markdown(f"*Error: Config file `{CONFIG_PATH}` not found.*"))
        except Exception as e:
            logging.error(f"Failed to open config file {CONFIG_PATH}: {e}")
            self.query_one("#chat-view").mount(Markdown(f"*Error opening `{CONFIG_PATH}`: {e}*"))
        self.query_one("#chat-input", Input).focus()

    @on(Button.Pressed, "#reload-config-button")
    def on_reload_config_button_pressed(self, event: Button.Pressed) -> None:
        """Reload MCP server configurations and re-initialize the agent."""
        logging.info("Reloading MCP configuration...")
        self.servers = self.load_mcp_servers_from_config()
        self.initialize_agent()
        if self.agent:
            server_names = []
            try:
                 with open(CONFIG_PATH, 'r') as f:
                    config_data = json.load(f)
                    server_names = list(config_data.get("mcpServers", {}).keys())
            except Exception as e:
                 logging.warning(f"Could not read server names from config during reload: {e}")

            self.query_one("#chat-view").mount(Markdown(f"*MCP Configuration reloaded. Servers: {', '.join(server_names) or 'None'}*"))
            logging.info(f"MCP configuration reloaded. Servers: {server_names}")
        else:
             self.query_one("#chat-view").mount(Markdown("*MCP Config reloaded, but agent initialization failed. Check logs.*"))
             logging.error("MCP configuration reloaded, but agent initialization failed.")

        self.query_one("#chat-input", Input).focus()

def main():
    """Entry point for the application."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(threadName)s - %(message)s',
        filename='app.log',
        filemode='w'
    )
    logging.info("Application starting.")
    app = TerminalApp()
    app.run()
    logging.info("Application finished.")

if __name__ == "__main__":
    main()