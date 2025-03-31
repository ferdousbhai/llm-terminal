# Gemini Terminal

A terminal-based UI for Google's Gemini AI with MCP tool integration. This application provides a text-based interface for interacting with Google's Gemini AI models while allowing integration with external tools through the MCP (Model Control Protocol) standard.

## Features

- Terminal UI built with Textual
- Google Gemini AI integration
- MCP server support for tool calling
- Configuration management
- Customizable system prompts

## Installation

You can install the package using `uv`:

```bash
uv pip install gemini-terminal
```

Or from source:

```bash
git clone https://github.com/yourusername/gemini-terminal.git
cd gemini-terminal
uv pip install -e .
```

## Usage

After installation, you can run the application using:

```bash
gemini-terminal
```

## Configuration

On first run, the application will create a configuration file at `~/.gemini_terminal.yaml`. You will need to set your Gemini API key in the settings (Ctrl+S).

## MCP Tool Integration

The application supports MCP servers for tool integration. You can add servers in the UI and toggle them on/off as needed.

## Development

```bash
# Clone the repository
git clone https://github.com/yourusername/gemini-terminal.git
cd gemini-terminal

# Install development dependencies
uv pip install -e ".[dev]"

# Run tests
pytest
```

## License

MIT
