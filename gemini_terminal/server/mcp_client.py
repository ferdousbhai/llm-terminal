from typing import List, Tuple, Any, Dict
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from gemini_terminal.data_models import ServerConfig

async def connect_to_server(server_config: ServerConfig) -> Tuple[ServerConfig, ClientSession, List[Any]]:
    """Connect to an MCP server and retrieve its tools"""
    server_params = StdioServerParameters(
        command=server_config.command,
        args=server_config.args,
        env=server_config.env or None
    )
    
    try:
        async with stdio_client(server_params) as (read, write):
            session = ClientSession(read, write)
            await session.initialize()
            
            # Get tools from this server
            mcp_tools = await session.list_tools()
            
            return server_config, session, mcp_tools.tools
    except Exception as e:
        raise ConnectionError(f"Failed to connect to MCP server {server_config.name}: {str(e)}") 