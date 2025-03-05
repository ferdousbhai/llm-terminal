# Terminal App

A Textual-based terminal application for interacting with language models using the Model Control Protocol (MCP).

## Prerequisites

- Python 3.12 or higher
- [uv](https://github.com/astral-sh/uv) - Fast Python package installer and environment manager
- An OpenAI API key (for accessing OpenAI models)

## Environment Setup

Before running the application, you need to set up your OpenAI API key as an environment variable:

### On macOS/Linux

```bash
export OPENAI_API_KEY=your-api-key-here
```

You can add this to your shell profile to make it permanent.

## Installation

1. Clone this repository:

   ```bash
   git clone <repository-url>
   cd terminal-app
   ```

2. Use `uv` to create a virtual environment and install dependencies:

   ```bash
   uv venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   uv sync
   ```

## Running the Application

After installing dependencies with `uv sync`:

```bash
uv run -m src.main
```

## Features

- Interactive terminal-based UI built with Textual
- Integration with the Model Control Protocol (MCP) - WORK IN PROGRESS
- Support for various language models (Coming soon)
- Tool calling capabilities (Coming soon)

## Controls

- Use the text input at the bottom to interact with the language model
- Configure MCP settings using the configuration button
- Select different models with the model selection button
- Start a new conversation using the new conversation button

## Configuration

The application can be configured through the interface using the "Configure MCP" button, where you can set parameters for connecting to MCP servers.
