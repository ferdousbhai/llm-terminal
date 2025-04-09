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

- Python 3.12 or higher
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

## Supported LLM Providers

This application leverages PydanticAI and comes pre-packaged with support for several major LLM providers. To use a specific provider, you need to:

1. **Enter the Model Identifier:** In the application's "Model" input field, provide the correct identifier for the model you wish to use. This usually follows the format `provider_name:model_name`. Examples: `openai:gpt-4o`, `anthropic:claude-3-5-sonnet-latest`, `cohere:command-r-plus`, `groq:llama3-70b-8192`.
2. **Set the API Key Environment Variable:** Before launching the application, set the appropriate environment variable for the provider.
    - `OPENAI_API_KEY=your_openai_key`
    - `ANTHROPIC_API_KEY=your_anthropic_key`
    - `CO_API_KEY=your_cohere_key`
    - `GROQ_API_KEY=your_groq_key`

The application will automatically detect and use these keys if the corresponding model identifier prefix (e.g., `openai:`, `anthropic:`) is used.

For more details on model identifiers and provider configuration, refer to the [PydanticAI Models Documentation](https://ai.pydantic.dev/models/).

## License

MIT
