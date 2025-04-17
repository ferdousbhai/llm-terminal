import json
import logging
import os
from typing import Any

from pydantic_ai.mcp import MCPServerStdio

SYSTEM = """You are a helpful AI assistant."""
MCP_CONFIG_PATH = "mcp_config.json"
SETTINGS_PATH = "settings.json"
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
DEFAULT_SETTINGS = {
    "model_identifier": "openai:o4-mini",
    "system_prompt": SYSTEM
}


def ensure_config_file(path: str = MCP_CONFIG_PATH) -> None:
    """Creates the default config file if it doesn't exist."""
    if not os.path.exists(path):
        logging.info(f"Configuration file not found at {path}. Creating default.")
        try:
            with open(path, 'w') as f:
                json.dump(DEFAULT_CONFIG, f, indent=2)
            logging.info(f"Default configuration file created at {path}.")
        except Exception as e:
            logging.error(f"Failed to create default configuration file at {path}: {e}")

def load_mcp_servers_from_config(path: str = MCP_CONFIG_PATH) -> dict[str, MCPServerStdio]:
    """Loads MCP server configurations from the JSON file."""
    servers_dict = {}
    try:
        with open(path, 'r') as f:
            config_data = json.load(f)

        mcp_servers_config = config_data.get("mcpServers", {})
        if not mcp_servers_config:
            logging.warning(f"No 'mcpServers' found or empty in {path}. No servers loaded.")
            return {}

        for server_name, server_details in mcp_servers_config.items():
            command = server_details.get("command")
            args = server_details.get("args")
            env = server_details.get("env")
            if command and isinstance(args, list):
                log_msg = f"Loading MCP server config '{server_name}' with command '{command}', args {args}"
                if env is not None:
                     log_msg += f", and env {env}"
                logging.info(log_msg)
                servers_dict[server_name] = MCPServerStdio(command, args=args, env=env)
            else:
                logging.warning(f"Skipping invalid config for server '{server_name}' in {path}.")

    except FileNotFoundError:
        logging.error(f"Configuration file not found at {path}. Cannot load servers.")
        ensure_config_file(path) # Attempt to create the default config
        # Do not recurse, return empty dict if file still doesn't exist or couldn't be created
        return {}
    except json.JSONDecodeError as e:
        logging.error(f"Error decoding JSON from {path}: {e}.")
        # Note: Cannot directly update UI from here. Consider returning error or raising.
    except Exception as e:
        logging.error(f"An unexpected error occurred while loading configuration from {path}: {e}")
        # Note: Cannot directly update UI from here.

    return servers_dict

def load_settings(path: str = SETTINGS_PATH) -> dict[str, Any]:
    """Loads application settings from the JSON file."""
    if not os.path.exists(path):
        logging.info(f"Settings file not found at {path}. Using defaults.")
        return DEFAULT_SETTINGS.copy() # Return a copy

    try:
        with open(path, 'r') as f:
            settings_data = json.load(f)
            # Validate or provide defaults for missing keys
            loaded_settings = {
                "model_identifier": settings_data.get("model_identifier", DEFAULT_SETTINGS["model_identifier"]),
                "system_prompt": settings_data.get("system_prompt", DEFAULT_SETTINGS["system_prompt"])
            }
            logging.info(f"Loaded settings from {path}: {loaded_settings}")
            return loaded_settings
    except json.JSONDecodeError as e:
        logging.error(f"Error decoding JSON from {path}: {e}. Using default settings.")
        return DEFAULT_SETTINGS.copy()
    except Exception as e:
        logging.error(f"An unexpected error occurred while loading settings from {path}: {e}. Using default settings.")
        return DEFAULT_SETTINGS.copy()

def save_settings(model_identifier: str, system_prompt: str, path: str = SETTINGS_PATH) -> bool:
    """Saves the current settings to the JSON file. Returns True on success, False on failure."""
    settings_to_save = {
        "model_identifier": model_identifier,
        "system_prompt": system_prompt
    }
    try:
        with open(path, 'w') as f:
            json.dump(settings_to_save, f, indent=2)
        logging.info(f"Settings saved to {path}: {settings_to_save}")
        return True
    except Exception as e:
        logging.error(f"Failed to save settings to {path}: {e}")
        return False