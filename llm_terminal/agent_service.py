import asyncio
import logging
from typing import Callable, AsyncGenerator, Any
from contextlib import AsyncExitStack

from pydantic_ai import Agent
from pydantic_ai.exceptions import AgentRunError, UserError
from pydantic_ai.messages import (
    ModelMessage,
    AgentStreamEvent,
)

from .config import load_mcp_servers_from_config

logger = logging.getLogger(__name__)

class AgentService:
    """Manages the lifecycle and interactions of the Pydantic-AI Agent using run_mcp_servers."""

    def __init__(self, log_to_chat_callback: Callable[[str], None]):
        """
        Initializes the AgentService.

        Args:
            log_to_chat_callback: A thread-safe callback to log messages to the main chat UI.
        """
        self.log_to_chat_callback = log_to_chat_callback
        self.model_identifier: str = ""
        self.system_prompt: str = ""
        self.agent: Agent | None = None
        self._mcp_stack: AsyncExitStack | None = None
        self._is_initialized = False
        self._lock = asyncio.Lock()
        self.message_history: list[ModelMessage] = []

    @property
    def is_initialized(self) -> bool:
        return self._is_initialized

    async def initialize(self, model_identifier: str, system_prompt: str):
        """Initializes the agent, resets history, and enters the run_mcp_servers context."""
        async with self._lock:
            if self._is_initialized:
                logger.warning("Agent service already initialized.")
                return

            logger.info(f"Initializing AgentService with model: {model_identifier}...")
            self.model_identifier = model_identifier
            self.system_prompt = system_prompt
            self._is_initialized = False # Mark as not initialized until successful completion
            self.message_history = [] # Clear history specifically on initialization
            self._mcp_stack = None # Ensure stack is clear before attempt
            self.agent = None # Ensure agent is clear before attempt

            try:
                mcp_server_configs = load_mcp_servers_from_config()
                mcp_servers = list(mcp_server_configs.values())
                logger.info(f"Loaded {len(mcp_servers)} MCP server configurations.")

                agent_kwargs: dict[str, Any] = {
                    "mcp_servers": mcp_servers,
                }
                if self.system_prompt:
                    agent_kwargs["system_prompt"] = self.system_prompt

                self.agent = Agent(self.model_identifier, **agent_kwargs)
                logger.info(f"Agent instance created for model {self.model_identifier}.")

                self._mcp_stack = AsyncExitStack()
                logger.info("Starting MCP servers via context manager...")
                await self._mcp_stack.enter_async_context(self.agent.run_mcp_servers())
                self._is_initialized = True
                logger.info("AgentService initialized and MCP servers started.")
                self.log_to_chat_callback(f"*Agent initialized successfully with model **{self.model_identifier}**.*")

            except (UserError, AgentRunError) as e:
                 logger.exception(f"Failed to create Agent instance with {self.model_identifier}: {e}")
                 self.log_to_chat_callback(f"*Error initializing Agent: {e}. Please check model identifier and configuration.*")
                 await self._cleanup_resources() # Cleanup on specific errors
            except Exception as e:
                logger.exception(f"Failed to initialize AgentService: {e}") # Use exception for stack trace
                self.log_to_chat_callback(f"*Error initializing Agent Service: {e}*")
                await self._cleanup_resources() # Cleanup on general errors

    async def _cleanup_resources(self):
        """Internal helper to clean up resources, used on error or shutdown."""
        logger.info("Cleaning up AgentService resources...")
        if self._mcp_stack:
            try:
                await self._mcp_stack.aclose()
            except Exception as close_err:
                logger.error(f"Error closing MCP stack during cleanup: {close_err}", exc_info=True)
        self.agent = None
        self._mcp_stack = None
        self._is_initialized = False
        # Keep history unless explicitly cleared elsewhere

    async def shutdown(self):
        """Exits the run_mcp_servers context and cleans up."""
        async with self._lock:
            if not self._is_initialized and not self._mcp_stack:
                logger.warning("Agent service not running or already shut down.")
                return

            logger.info("Shutting down AgentService...")
            await self._cleanup_resources()
            logger.info("AgentService shut down complete.")

    async def reinitialize(self, model_identifier: str, system_prompt: str):
        """Shuts down the current agent/servers and initializes a new instance. History is cleared."""
        logger.info(f"Reinitializing AgentService with model: {model_identifier}...")
        await self.shutdown()
        await self.initialize(model_identifier, system_prompt) # Initialize clears history

    async def clear_history(self):
        """Clears the internal message history."""
        async with self._lock:
            logger.info("Clearing internal message history.")
            self.message_history = []
            self.log_to_chat_callback("*Chat history cleared.*")

    async def process_prompt_stream(
        self, prompt: str
    ) -> AsyncGenerator[AgentStreamEvent, None] | None:
        """
        Processes a user prompt using the agent's stream and internal history.
        Updates internal history after the stream is exhausted.

        Yields:
            AgentStreamEvent objects from the agent's stream.

        Returns:
            An async generator, or None if the agent is not initialized.
        """
        if not self.agent or not self._is_initialized:
            logger.error("Agent service not initialized. Cannot process message.")
            return None # This is now allowed as the outer function is not the generator

        logger.debug(f"Processing prompt stream for model {self.model_identifier}: {prompt[:50]}...")

        async def generator() -> AsyncGenerator[AgentStreamEvent, None]:
            run_result = None # Initialize without type hint
            try:
                # Directly use the context manager and yield from the stream
                async with self.agent.run_stream(prompt, message_history=self.message_history) as run_result:
                    async for event in run_result.stream():
                        yield event
                    logger.debug("Agent stream processing finished.")

                    # Update internal history AFTER stream is exhausted but before exiting context
                    try:
                        final_history = run_result.all_messages()
                        if final_history:
                            async with self._lock: # Protect history update
                                self.message_history = final_history
                            logger.debug(f"AgentService internal history updated. Length: {len(self.message_history)}")
                        else:
                            logger.warning("run_result.all_messages() returned empty after stream.")
                    except Exception as hist_err:
                        logger.exception(f"Error updating internal message history: {hist_err}")
                        # Decide if this error should propagate or just be logged.
                        # For now, logging it. The stream itself succeeded.

            except Exception as e:
                logger.exception(f"Error during agent stream processing: {e}")
                # If an error occurs during streaming, we might not have a valid run_result
                # to update history from. The stream might have been interrupted.
                # Consider how to handle partial history or simply log the error.
                # Re-raise or yield an error event? For now, just logging and returning.
                # Let's yield a string error message so the UI knows.

                # Yielding error string within the generator itself:
                # Convert the exception to a string AgentStreamEvent if possible, or just log.
                # For simplicity, we'll just log here. The outer function handles agent init errors.
                # The UI in app.py already handles exceptions during the iteration.
                pass # Error is logged, generator stops.

        return generator() # Return the async generator object