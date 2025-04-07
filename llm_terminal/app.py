import logging
from datetime import datetime

from textual import on, work
from textual.app import App, ComposeResult
from textual.widgets import Header, Input, Footer, Markdown, Button
from textual.containers import VerticalScroll, Horizontal

from pydantic_ai import Agent
from pydantic_ai.mcp import MCPServerStdio

# Define a system prompt
SYSTEM = """You are a helpful AI assistant."""

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

    Horizontal { /* Ensure the button/input row takes minimal height */
        height: auto;
    }
    """

    def compose(self) -> ComposeResult:
        """Compose the UI layout"""
        yield Header()
        with VerticalScroll(id="chat-view"):
            yield Response(f"# {self.get_time_greeting()} How can I help?")
        with Horizontal():
            yield Button("New Chat", id="new-chat-button")
            yield Input(placeholder="Ask me anything...")
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
        """Initialize the agent and MCP server on app mount"""
        # Define the MCP server for Python code execution
        run_python_server = MCPServerStdio(
            'deno',
            args=[
                'run',
                '-N',
                '-R=node_modules',
                '-W=node_modules',
                '--node-modules-dir=auto',
                'jsr:@pydantic/mcp-run-python',
                'stdio',
            ]
        )
        self.servers = [run_python_server]
        # Store the model identifier string
        self.model_identifier = "openai:gpt-4o"
        # Create the agent with the MCP server
        self.agent = Agent(self.model_identifier, system_prompt=SYSTEM, mcp_servers=self.servers)
        # Initialize message history
        self.message_history = []

    @on(Input.Submitted)
    async def on_input(self, event: Input.Submitted) -> None:
        """Handle input submissions"""
        chat_view = self.query_one("#chat-view")
        prompt = event.value
        event.input.clear()

        # Display user prompt
        await chat_view.mount(Prompt(f"**You:** {prompt}"))

        # Create a response widget and anchor it
        await chat_view.mount(response := Response())
        response.anchor()

        # Process the prompt
        self.process_prompt(prompt, response)
        logging.info(f"Input submitted: {prompt}")

    @work(thread=True)
    async def process_prompt(self, prompt: str, response: Response) -> None:
        """Process the prompt with the agent and update the response"""
        logging.info(f"Processing prompt: {prompt}")
        # Use the model identifier for the prefix
        response_content = f"**{self.model_identifier}:** "
        self.call_from_thread(response.update, response_content)

        # Use message history and stream the response within MCP context
        try:
            async with self.agent.run_mcp_servers():
                logging.info("MCP servers started.")
                # Stream the response using async context manager, passing history
                async with self.agent.run_stream(prompt, message_history=self.message_history) as run_result:
                    logging.info("Agent stream started.")
                    async for accumulated_chunk in run_result.stream():
                        response_content = f"**{self.model_identifier}:** {accumulated_chunk}"
                        logging.info(f"Updating response widget with: {response_content!r}")
                        self.call_from_thread(response.update, response_content)

                    # Update message history after the stream completes
                    self.message_history = run_result.all_messages()
                    logging.info(f"Message history updated. Length: {len(self.message_history)}")

            logging.info("MCP servers stopped.")
        except Exception as e:
            logging.exception(f"Error during prompt processing: {e}")
            self.call_from_thread(response.update, f"{response_content}\n\n**Error:** {e}")

        # Final display state is handled within the loop's last update
        logging.debug(f"Final response content after history update: {response_content}")

    @on(Button.Pressed, "#new-chat-button")
    async def on_new_chat_button_pressed(self, event: Button.Pressed) -> None:
        """Handle the 'New Chat' button press."""
        logging.info("'New Chat' button pressed. Clearing history and display.")
        # Clear the message history
        self.message_history = []

        # Clear the chat view
        chat_view = self.query_one("#chat-view")
        await chat_view.remove_children()

        # Add the initial greeting back
        await chat_view.mount(Response(f"# {self.get_time_greeting()} How can I help?"))

        # Focus the input again
        self.query_one(Input).focus()

def main():
    """Entry point for the application."""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,  # Changed from DEBUG to INFO
        format='%(asctime)s - %(levelname)s - %(threadName)s - %(message)s',
        filename='app.log',  # Log to a file
        filemode='w'  # Overwrite the log file each time
    )
    logging.info("Application starting.")
    app = TerminalApp()
    app.run()
    logging.info("Application finished.")

if __name__ == "__main__":
    main()