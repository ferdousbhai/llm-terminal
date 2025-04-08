# LLM Terminal

A terminal-based UI for interacting with LLMs through PydanticAI, featuring dynamic configuration and MCP tool integration.

## Features

- **Terminal UI:** Built with Textual.
- **LLM Interaction:** Powered by PydanticAI with streaming markdown responses.
- **Model & Prompt Configuration:** Change the LLM model identifier and system prompt on-the-fly.
- **MCP Integration:** Executes tools (like Python code) via MCP servers defined in `mcp_config.json`.
- **Dynamic Configuration:** Load MCP servers from `mcp_config.json`.
- **Chat Management:** Start new chat sessions easily.
- **Logging:** Session activity logged to `app.log`.

## Prerequisites

- Python 3.10 or higher
- Deno (required by the default MCP Python server)

## Installation

```bash
git clone https://github.com/ferdousbhai/llm-terminal.git
cd llm-terminal
uv sync
```

## Configuration

The application uses `mcp_config.json` to define MCP servers. A default configuration for running Python code is created if the file doesn't exist. You can edit this file directly via the "Edit MCP Config" button within the app and reload it using the "Reload MCP Config" button.

## Usage

```bash
uv run llm-terminal
```

## License

MIT
