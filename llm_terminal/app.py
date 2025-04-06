from datetime import datetime

from textual import on, work
from textual.app import App, ComposeResult
from textual.widgets import Header, Input, Footer, Markdown
from textual.containers import VerticalScroll

from pydantic_ai import Agent
from pydantic_ai.mcp import MCPServerStdio

# Define a system prompt
SYSTEM = """You are a helpful AI assistant."""

class Prompt(Markdown):
    """Widget for user prompts"""
    pass

class Response(Markdown):
    """Widget for AI responses"""
    BORDER_TITLE = "AI"

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
    """

    def compose(self) -> ComposeResult:
        """Compose the UI layout"""
        yield Header()
        with VerticalScroll(id="chat-view"):
            yield Response(f"# {self.get_time_greeting()} How can I help?")
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
        self.server = MCPServerStdio(
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
        # Create the agent with the MCP server
        self.agent = Agent("openai:gpt-4o", system_prompt=SYSTEM, mcp_servers=[self.server])
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

    @work(thread=True)
    async def process_prompt(self, prompt: str, response: Response) -> None:
        """Process the prompt with the agent and update the response"""
        response_content = "**AI:** "

        # Process the prompt with the agent inside a context manager
        async with self.agent.run_mcp_servers():
            # Use message history for context
            result = await self.agent.run(prompt, message_history=self.message_history)

            # Update message history with new messages
            self.message_history = result.all_messages()

            if hasattr(result, 'data'):
                response_content += result.data
            else:
                response_content += "I couldn't generate a response."

            self.call_from_thread(response.update, response_content)

def main():
    """Entry point for the application."""
    app = TerminalApp()
    app.run()

if __name__ == "__main__":
    main()