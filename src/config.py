import json
from pathlib import Path

from pydantic import BaseModel, Field

CONFIG_PATH = Path.home() / ".config" / "minimalist-mpc" / "config.json"
DEFAULT_SYSTEM_PROMPT = """Formulate all responses as if you were a sentient AI."""

class ServerConfig(BaseModel):
    name: str = "Default Server"
    command: str = "python"
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True

class AppConfig(BaseModel):
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    servers: list[ServerConfig] = Field(default_factory=list)

    @classmethod
    def load(cls, config_path: Path | None = None) -> 'AppConfig':
        config_path = config_path or CONFIG_PATH

        if not config_path.exists():
            return cls()

        with open(config_path) as f:
            data = json.load(f)
            
            # Handle migration from old format to new
            if 'command' in data and 'servers' not in data:
                # Create a server from top-level command/args if they exist
                server = ServerConfig(
                    name="Migrated Server",
                    command=data.get('command', ''),
                    args=data.get('args', []),
                    env=data.get('env', {})
                )
                data['servers'] = [server.model_dump()]
                
                # Remove old fields
                data.pop('command', None)
                data.pop('args', None)
                data.pop('env', None)
            
            # Migrate any servers with default names
            if 'servers' in data:
                for i, server in enumerate(data['servers']):
                    # If a server has the default name, generate a more descriptive one
                    if server.get('name') == "Default Server":
                        command = server.get('command', '')
                        if command:
                            # Generate a name based on the command
                            base_name = command.split("/")[-1]
                            data['servers'][i]['name'] = f"{base_name} Server {i+1}"
                        else:
                            # Fallback if no command
                            data['servers'][i]['name'] = f"MCP Server {i+1}"

            return cls(**data)

    def save(self, config_path: Path | None = None) -> None:
        config_path = config_path or CONFIG_PATH
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, 'w') as f:
            json.dump(self.model_dump(), f, indent=2)