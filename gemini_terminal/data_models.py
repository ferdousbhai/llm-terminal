from dataclasses import dataclass, asdict, field

@dataclass
class ServerConfig:
    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    active: bool = False

@dataclass
class AppConfig:
    gemini_api_key: str = ""
    system_prompt: str = "You are a sentient AI assistant."
    model: str = "gemini-2.5-pro-exp-03-25"
    servers: list[ServerConfig] = field(default_factory=list) 