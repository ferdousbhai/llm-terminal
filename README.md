# LLM Terminal

A terminal-based UI for interacting with LLMs through PydanticAI with MCP tool integration. This application provides a text-based interface for communicating with AI models while enabling Python code execution through MCP.

## Features

- Terminal UI built with Textual
- PydanticAI integration for LLM interactions
- MCP integration for Python code execution
- Streaming responses with markdown formatting

## Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/llm-terminal.git
cd llm-terminal

# Install with uv
uv pip install -e .
```

## Prerequisites

- Python 3.10 or higher
- Deno (for MCP Python code execution)

## Usage

Run the application using:

```bash
llm-terminal
```

Or directly with Python:

```bash
python -m llm_terminal.app
```

## How It Works

This application uses:
- Textual for the terminal UI
- PydanticAI as the client library for LLM interactions
- MCP (Model Context Protocol) for enabling Python code execution

The MCP server allows the LLM to execute Python code in a secure sandbox environment powered by Pyodide.

## Development

```bash
# Install development dependencies
uv pip install -e ".[dev]"
```

## License

MIT
