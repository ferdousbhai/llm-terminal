import os
import yaml
from typing import Dict, Any

from gemini_terminal.data_models import AppConfig, ServerConfig

class ConfigManager:
    """Handles loading and saving of application configuration"""
    
    def __init__(self, config_path: str = "~/.gemini_terminal.yaml"):
        self.config_path = os.path.expanduser(config_path)
    
    def load_config(self) -> AppConfig:
        """Load configuration from a YAML file"""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r') as f:
                    data = yaml.safe_load(f)
                    
                    # Convert server data to ServerConfig objects
                    servers = []
                    for server_data in data.get('servers', []):
                        servers.append(ServerConfig(**server_data))
                        
                    data['servers'] = servers
                    return AppConfig(**data)
        except Exception as e:
            print(f"Error loading config: {e}")
        
        return AppConfig()
    
    def save_config(self, config: AppConfig) -> None:
        """Save configuration to a YAML file"""
        try:
            # Convert config to dict
            config_dict = config.__dict__
            
            # Ensure directory exists
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            
            with open(self.config_path, 'w') as f:
                yaml.dump(config_dict, f)
                
        except Exception as e:
            print(f"Error saving config: {e}") 