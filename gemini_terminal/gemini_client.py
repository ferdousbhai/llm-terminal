from google import genai
from google.genai import types
from typing import List, Tuple, Any, Callable

class GeminiClient:
    """Client for interacting with Google's Gemini API"""
    
    def __init__(self, api_key: str = "", model: str = "gemini-2.5-pro-exp-03-25"):
        self.api_key = api_key
        self.model_name = model
        self.client = None
        
        if api_key:
            self.initialize(api_key, model)
    
    def initialize(self, api_key: str, model: str = "gemini-2.5-pro-exp-03-25") -> None:
        """Initialize the Gemini client with API key"""
        self.api_key = api_key
        self.model_name = model
        self.client = genai.Client(api_key=api_key)
    
    async def verify_api_key(self) -> Tuple[bool, str]:
        """Verify the API key works by making a simple call to the model
        
        Returns:
            Tuple of (success, message)
        """
        if not self.client:
            return False, "No API key configured"
            
        try:
            contents = [types.Content(parts=[types.Part(text="Hello, are you working?")])]
            
            response = await self.client.aio.models.generate_content(
                model=self.model_name,
                contents=contents,
                config=types.GenerateContentConfig(
                    temperature=0.0,
                    max_output_tokens=10
                ),
            )
            
            if response and response.candidates:
                return True, "API key verified successfully"
            else:
                return False, "Failed to get response from model"
                
        except Exception as e:
            return False, f"API key verification failed: {str(e)}"
    
    def generate_content(
        self, 
        system_prompt: str, 
        user_prompt: str, 
        on_chunk: Callable[[str], None]
    ) -> None:
        """Generate a response from Gemini without MCP"""
        if not self.client:
            on_chunk("Please set your Gemini API key in settings (Ctrl+S)")
            return
            
        try:
            response_text = ""
            
            config = types.GenerateContentConfig(
                temperature=0.7,
            )
            
            contents = [
                types.Content(role="user", parts=[types.Part(text=system_prompt)]),
                types.Content(role="model", parts=[types.Part(text="I'll help you with that.")]),
                types.Content(role="user", parts=[types.Part(text=user_prompt)])
            ]
            
            response = self.client.models.generate_content_stream(
                model=self.model_name,
                contents=contents,
                config=config
            )
            
            for chunk in response:
                if chunk.text:
                    response_text += chunk.text
                    on_chunk(response_text)
                
        except Exception as e:
            error_message = f"Error: {str(e)}"
            on_chunk(error_message)
    
    async def generate_mcp_content(
        self,
        system_prompt: str,
        user_prompt: str,
        mcp_sessions: List[Tuple[Any, Any, List[Any]]],
        mcp_tools: List[types.Tool],
        on_update: Callable[[str], None]
    ) -> None:
        """Generate a response using Gemini with MCP integration"""
        if not self.client:
            await on_update("Please set your Gemini API key in settings (Ctrl+S)")
            return
            
        try:
            response_text = ""
            
            # Prepare initial chat content
            contents = [
                types.Content(role="user", parts=[types.Part(text=system_prompt)]),
                types.Content(role="model", parts=[types.Part(text="I'll help you with that.")]),
                types.Content(role="user", parts=[types.Part(text=user_prompt)])
            ]
            
            # Initial request with user prompt and function declarations
            response = await self.client.aio.models.generate_content(
                model=self.model_name,
                contents=contents,
                config=types.GenerateContentConfig(
                    temperature=0.7,
                    tools=mcp_tools,
                ),
            )
            
            # Append initial response to contents
            contents.append(response.candidates[0].content)
            
            # Update the UI with initial response
            initial_response = response.candidates[0].content.parts[0].text if response.candidates else ""
            await on_update(initial_response or "Thinking...")
            response_text = initial_response or ""
            
            # Tool Calling Loop
            turn_count = 0
            max_tool_turns = 5
            while response.function_calls and turn_count < max_tool_turns:
                turn_count += 1
                tool_response_parts = []
                
                # Process all function calls
                for fc_part in response.function_calls:
                    tool_name = fc_part.name
                    args = fc_part.args or {}
                    
                    await on_update(f"{response_text}\n\n*Using tool: {tool_name}...*")
                    
                    # Find the appropriate session for this tool
                    found = False
                    for server_config, session, tools in mcp_sessions:
                        if any(tool.name == tool_name for tool in tools):
                            try:
                                # Call the tool
                                tool_result = await session.call_tool(tool_name, args)
                                
                                if tool_result.isError:
                                    tool_response = {"error": tool_result.content[0].text}
                                else:
                                    tool_response = {"result": tool_result.content[0].text}
                                    
                                found = True
                                break
                            except Exception as e:
                                tool_response = {"error": f"Tool execution failed: {str(e)}"}
                                found = True
                                break
                    
                    if not found:
                        tool_response = {"error": f"Tool '{tool_name}' not found in active servers"}
                    
                    # Prepare function response
                    tool_response_parts.append(
                        types.Part.from_function_response(
                            name=tool_name, response=tool_response
                        )
                    )
                
                # Add tool responses to history
                contents.append(types.Content(role="user", parts=tool_response_parts))
                
                # Make next call to model
                response = await self.client.aio.models.generate_content(
                    model=self.model_name,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        temperature=0.7,
                        tools=mcp_tools,
                    ),
                )
                
                # Get updated text
                new_response_text = response.candidates[0].content.parts[0].text if response.candidates else ""
                response_text = new_response_text or response_text
                await on_update(response_text)
                
                # Add model response to history
                contents.append(response.candidates[0].content)
            
            # Final update
            if turn_count >= max_tool_turns and response.function_calls:
                response_text += "\n\n*Maximum tool turns reached*"
                await on_update(response_text)
            
        except Exception as e:
            error_message = f"Error: {str(e)}"
            await on_update(error_message)