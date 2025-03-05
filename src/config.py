from dataclasses import dataclass
import json
from pathlib import Path

@dataclass
class MCPConfig:
    command: str = "python"
    args: list[str] = None
    env: dict[str, str] | None = None

    @classmethod
    def load(cls, config_path: Path = None) -> 'MCPConfig':
        if config_path is None:
            config_path = Path.home() / ".config" / "minimalist-mpc" / "config.json"

        if not config_path.exists():
            return cls()

        with open(config_path) as f:
            data = json.load(f)
            return cls(**data)

    def save(self, config_path: Path = None) -> None:
        if config_path is None:
            config_path = Path.home() / ".config" / "minimalist-mpc" / "config.json"

        config_path.parent.mkdir(parents=True, exist_ok=True)

        with open(config_path, 'w') as f:
            json.dump({
                'command': self.command,
                'args': self.args or [],
                'env': self.env or {},
            }, f, indent=2)