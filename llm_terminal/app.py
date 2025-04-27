import logging
import os
import platform
import subprocess
from datetime import datetime
from logging import FileHandler
import sys
import asyncio
import threading
import queue

from textual import on, work
from textual.app import App, ComposeResult
from textual.widgets import Header, Input, Footer, Markdown, Button, Label
from textual.containers import VerticalScroll, Horizontal
from textual.worker import WorkerState, Worker


from .config import (
    MCP_CONFIG_PATH,
    SETTINGS_PATH,
    ensure_config_file,
    load_settings,
    save_settings
)
from .agent_service import AgentService

# Simplified logging setup at module level
log = logging.getLogger(__name__)

class Prompt(Markdown):
    """Widget for user prompts"""
    pass

class Response(Markdown):
    """Widget for AI responses"""
    pass

class TerminalApp(App):
    """A terminal-based chat interface for PydanticAI with MCP integration"""
    AUTO_FOCUS = "Input"
    CSS = """
    Prompt { background: $primary 10%; color: $text; margin: 1; margin-right: 8; padding: 1 2 0 2; }
    Response { border: wide $success; background: $success 10%; color: $text; margin: 1; margin-left: 8; padding: 1 2 0 2; }
    #chat-view { height: 1fr; }
    Horizontal { height: auto; }
    Label.label { margin: 1 1 1 2; width: 15; text-align: right; }
    #system-prompt-input, #model-input { width: 1fr; }
    #config-buttons { height: auto; margin-top: 1; align: center middle; }
    """

    model_identifier: str
    system_prompt: str
    prompt_queue: queue.Queue[tuple[str, Response | None] | None]
    agent_worker_instance: Worker | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            yield Label("Model:", classes="label")
            yield Input(id="model-input", placeholder="Model (e.g., openai:gpt-4o)")
        with Horizontal():
            yield Label("System Prompt:", classes="label")
            yield Input(id="system-prompt-input", placeholder="Enter system prompt...")
        with Horizontal(id="config-buttons"):
            yield Button("Edit MCP Config", id="edit-config-button")
            yield Button("Reload MCP Config", id="reload-config-button")
        with VerticalScroll(id="chat-view"):
            yield Response(f"# {self.get_time_greeting()} How can I help?")
        with Horizontal():
            yield Button("New Chat", id="new-chat-button")
            yield Input(id="chat-input", placeholder="Ask me anything...")
        yield Footer()

    def get_time_greeting(self) -> str:
        hour = datetime.now().hour
        if 5 <= hour < 12:
            return "Good morning!"
        if 12 <= hour < 18:
            return "Good afternoon!"
        return "Good evening!"

    def on_mount(self) -> None:
        ensure_config_file()
        loaded_settings = load_settings()
        self.model_identifier = loaded_settings["model_identifier"]
        self.system_prompt = loaded_settings["system_prompt"]

        self.query_one("#model-input", Input).value = self.model_identifier
        self.query_one("#system-prompt-input", Input).value = self.system_prompt

        self.prompt_queue = queue.Queue()
        self._start_agent_worker()
        self.query_one("#chat-input", Input).focus()

    async def on_unmount(self) -> None:
        log.info("Stopping agent worker...")
        await self._stop_agent_worker()

    def _start_agent_worker(self):
        if self.agent_worker_instance and self.agent_worker_instance.state == WorkerState.RUNNING:
            log.warning("Agent worker already running.")
            return
        log.info(f"Starting agent worker for model '{self.model_identifier}'...")
        self.agent_worker_instance = self.agent_worker(self.model_identifier, self.system_prompt)

    async def _stop_agent_worker(self):
        terminal_states = {WorkerState.CANCELLED, WorkerState.ERROR, WorkerState.SUCCESS}
        
        worker_instance = self.agent_worker_instance
        
        if not worker_instance:
            log.info("_stop_agent_worker: No worker instance found.")
            return

        # Log the initial state
        initial_state = worker_instance.state
        log.info(f"_stop_agent_worker: Initial worker state: {initial_state}")

        # Always try to unblock the queue
        log.info("Signalling agent worker to stop via queue...")
        try:
            self.prompt_queue.put(None)
        except Exception as e:
            log.error(f"Error putting None into prompt_queue: {e}")

        # Now check state again and cancel if needed
        current_state = worker_instance.state 

        if current_state not in terminal_states:
            log.info(f"_stop_agent_worker: Worker state ({current_state}) is not terminal, requesting cancellation.")
            try:
                await self.workers.cancel_group(self, "agent_group")
                log.info("Agent worker group cancellation requested.")
                await asyncio.sleep(0.1) # Short delay to allow cancellation processing
                final_state = worker_instance.state
                log.info(f"_stop_agent_worker: State after cancellation attempt: {final_state}")
            except Exception as e:
                 log.error(f"Error during worker cancellation: {e}")
        else:
            log.info(f"_stop_agent_worker: Worker state ({current_state}) already terminal, skipping cancellation request.")

        self.agent_worker_instance = None # Ensure it's cleared
        log.info("_stop_agent_worker: Finished.")

    @work(thread=True, group="agent_group", exclusive=True, description="Agent Service Background Thread")
    def agent_worker(self, model_id: str, sys_prompt: str) -> None:
        """Runs AgentService lifecycle and prompt processing in a background thread."""
        worker_ident = threading.get_ident()
        log.info(f"[Worker Thread {worker_ident}] Starting agent logic...")
        async def _run_async_agent_logic():
            agent_service = AgentService(log_to_chat_callback=self._log_to_chat)
            initialized_successfully = False
            log.info(f"[Worker {worker_ident}] Initializing AgentService for {model_id}...")
            try:
                await agent_service.initialize(model_id, sys_prompt)
                initialized_successfully = agent_service.is_initialized

                if not initialized_successfully:
                    log.error("[Worker] AgentService failed to initialize.")
                    self.call_from_thread(self._log_to_chat, "*Agent worker failed to initialize. See logs.*", False)
                    return

                log.info("[Worker] AgentService initialized. Waiting for prompts...")
                while True:
                    item = self.prompt_queue.get()

                    if item is None:
                        log.info(f"[Worker {worker_ident}] Received stop signal (None).")
                        self.prompt_queue.task_done()
                        break # Exit the loop

                    prompt, response_widget = item

                    # Handle special signals
                    if prompt == "__CLEAR_HISTORY__":
                        log.info("[Worker] Received clear history signal.")
                        if agent_service and agent_service.is_initialized:
                            await agent_service.clear_history()
                        else:
                            log.warning("[Worker] Agent not initialized, cannot clear history.")
                        self.prompt_queue.task_done()
                        continue # Skip processing as a prompt

                    # Ensure we have a response widget for actual prompts
                    if response_widget is None:
                        log.error(f"[Worker] Received prompt '{prompt[:20]}...' without a Response widget. Skipping.")
                        self.prompt_queue.task_done()
                        continue

                    log.info(f"[Worker] Processing prompt: {prompt[:50]}...")
                    # Initialize outside try block for use in except/finally
                    current_cumulative_text = ""
                    first_chunk_received = False # Track if we've received the first chunk

                    try:
                        # Call process_prompt_stream without passing history
                        stream_generator = await agent_service.process_prompt_stream(prompt)

                        if stream_generator is None:
                            log.error("[Worker] Failed to get stream generator (AgentService likely not initialized).")
                            error_message = f"**{agent_service.model_identifier}:** -- **Error: Agent not ready or failed to start stream.**"
                            self.call_from_thread(response_widget.update, error_message)
                        else:
                            # Handle the stream
                            async for event in stream_generator:
                                log.debug(f"[Worker Stream] Received event: type={type(event).__name__}, event={event!r}")

                                if isinstance(event, str):
                                    current_cumulative_text = event # Track last text
                                    content_to_display = f"**{agent_service.model_identifier}:** {current_cumulative_text}"

                                    # Removed first_chunk_received check for loading=False
                                    # The first update will replace the placeholder
                                    first_chunk_received = True
                                    log.debug(f"[Worker Stream] Updating UI with content: '{content_to_display[:100]}...'")
                                    self.call_from_thread(response_widget.update, content_to_display)
                                    self.call_from_thread(response_widget.scroll_visible)
                                    await asyncio.sleep(0.01) # Throttle UI updates

                            # If the stream finished but we never received a text chunk, update the placeholder
                            if not first_chunk_received:
                                 log.debug("[Worker Stream] Stream finished without text event. Updating placeholder.")
                                 final_message = f"**{agent_service.model_identifier}:** (Processing complete)" # Or similar
                                 self.call_from_thread(response_widget.update, final_message)

                            log.debug(f"[Worker Stream] Exiting loop. Final text received: '{current_cumulative_text[:100]}...'")
                            log.debug("[Worker] Stream processing finished.")

                    except Exception as e:
                        log.exception(f"[Worker] Error during agent prompt processing: {e}")
                        # Update placeholder with error message
                        error_message = f"**{agent_service.model_identifier}:** -- **Error processing response.**"
                        self.call_from_thread(response_widget.update, error_message)

                    finally:
                        self.prompt_queue.task_done()

            except asyncio.CancelledError:
                log.info(f"[Worker {worker_ident}] Agent task (_run_async_agent_logic) explicitly cancelled.")
                # If cancelled while processing a prompt, mark task as done
                if 'item' in locals() and item is not None:
                    log.info(f"[Worker {worker_ident}] Marking task done due to cancellation during processing.")
                    self.prompt_queue.task_done()
            finally:
                log.info(f"[Worker {worker_ident}] Exiting _run_async_agent_logic.")

        try:
            # log.info(f"[Worker Thread {threading.get_ident()}] Starting agent logic...") # Moved inside
            asyncio.run(_run_async_agent_logic())
            log.info(f"[Worker Thread {worker_ident}] Agent logic finished normally.")
        except Exception as e:
             log.exception(f"[Worker Thread {worker_ident}] Error running agent async logic: {e}")
             self.call_from_thread(self._log_to_chat, f"*Agent worker thread critical error: {e}. See logs.*", False)
        finally:
             log.info(f"[Worker Thread {worker_ident}] Exiting agent_worker method.")

    @on(Input.Submitted, "#chat-input")
    async def on_input(self, event: Input.Submitted) -> None:
        chat_view = self.query_one("#chat-view")
        prompt = event.value.strip()
        event.input.clear()

        if not prompt:
            return

        await chat_view.mount(Prompt(f"**You:** {prompt}"))
        placeholder_text = f"**{self.model_identifier}:** 💭"
        response_widget = Response(placeholder_text)
        await chat_view.mount(response_widget)
        response_widget.scroll_visible()

        if self.agent_worker_instance and self.agent_worker_instance.state == WorkerState.RUNNING:
             log.debug(f"Queueing prompt: {prompt[:50]}...")
             self.prompt_queue.put((prompt, response_widget))
        else:
            log.error("Agent worker not running. Cannot process prompt.")
            await response_widget.update("*Error: Agent worker not ready.*")

    @on(Input.Submitted, "#model-input")
    @on(Input.Submitted, "#system-prompt-input")
    async def on_settings_change_submitted(self, event: Input.Submitted) -> None:
        widget_id = event.input.id
        needs_restart = False

        if widget_id == "model-input":
            new_model = event.value.strip()
            if new_model and new_model != self.model_identifier:
                log.info(f"Model changed: {self.model_identifier} -> {new_model}")
                self.model_identifier = new_model
                self._log_to_chat(f"*Model set to **{self.model_identifier}**. Re-initializing agent...*", False)
                needs_restart = True
            elif not new_model:
                log.warning("Model input submitted empty.")
                event.input.value = self.model_identifier # Restore
                self.query_one("#chat-input", Input).focus()
                return # Don't restart if value is invalid/unchanged
        else: # system-prompt-input
            new_prompt = event.value
            if new_prompt != self.system_prompt:
                log.info(f"System prompt updated (first 50 chars): '{new_prompt[:50]}...'")
                self.system_prompt = new_prompt
                self._log_to_chat("*System prompt updated. Re-initializing agent...*", False)
                needs_restart = True

        if needs_restart:
            if not save_settings(self.model_identifier, self.system_prompt):
                self._log_to_chat(f"*Error saving settings to `{SETTINGS_PATH}`*", False)
            log.info("Restarting agent worker due to settings change...")
            await self._stop_agent_worker()
            self._start_agent_worker()

        self.query_one("#chat-input", Input).focus()


    @on(Button.Pressed)
    async def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id
        if btn_id == "new-chat-button":
            log.info("New chat requested.")
            # Clear visual chat display
            chat_view = self.query_one("#chat-view")
            await chat_view.remove_children()
            await chat_view.mount(Response(f"# {self.get_time_greeting()} How can I help?"))
            # Send signal to worker thread to clear its history
            if self.agent_worker_instance and self.agent_worker_instance.state == WorkerState.RUNNING:
                log.info("Sending clear history signal to agent worker.")
                self.prompt_queue.put(("__CLEAR_HISTORY__", None))
            else:
                log.warning("Agent worker not running, cannot send clear history signal.")
                self._log_to_chat("*Agent not running, unable to clear history state.*")
        elif btn_id == "edit-config-button":
            log.info(f"Opening config file: {MCP_CONFIG_PATH}")
            self._open_file_in_editor(MCP_CONFIG_PATH)
        elif btn_id == "reload-config-button":
            log.info("Reloading MCP config and restarting agent...")
            self._log_to_chat("*Reloading MCP Configuration and re-initializing agent...*")
            await self._stop_agent_worker()
            self._start_agent_worker()
        self.query_one("#chat-input", Input).focus()

    def _log_to_chat(self, text: str, use_call_from_thread: bool = True) -> None:
        """Mount Markdown text to chat view, handling thread safety."""
        widget = Markdown(text)
        chat_view = self.query_one("#chat-view", VerticalScroll) # Ensure correct type hint/query

        # Simplified thread check and dispatch
        if use_call_from_thread and threading.current_thread() is not threading.main_thread():
            try:
                self.call_from_thread(chat_view.mount, widget)
                self.call_from_thread(widget.scroll_visible)
            except Exception as e:
                log.error(f"Error in call_from_thread within _log_to_chat: {e}", exc_info=True)
        elif self.is_running: # In main thread or explicitly told not to use call_from_thread
             try:
                 # Use call_later for safety even in main thread if app is running
                 self.call_later(chat_view.mount, widget)
                 self.call_later(widget.scroll_visible)
             except Exception as e:
                 log.error(f"Error in direct/call_later mount within _log_to_chat: {e}", exc_info=True)
        # else: App not running yet, mounting might fail, rely on standard logging

    def _open_file_in_editor(self, path: str) -> None:
        """Open a file in the default system editor."""
        log.info(f"Attempting to open '{path}' in editor.")
        try:
            system = platform.system()
            if system == "Windows":
                os.startfile(path)
            elif system == "Darwin":
                subprocess.run(["open", path], check=True)
            else:
                subprocess.run(["xdg-open", path], check=True)
            self._log_to_chat(f"*Opened `{path}`. Reload MCP Config after saving.*", False)
        except (FileNotFoundError, subprocess.CalledProcessError, Exception) as e:
            log.error(f"Failed to open file '{path}' in editor: {e}")
            self._log_to_chat(f"*Error opening `{path}`: {e}*", False)


def setup_logging():
    """Configure logging for the application."""
    log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(threadName)s - %(name)s - %(message)s')
    log_handler = FileHandler('app.log', mode='w')
    log_handler.setFormatter(log_formatter)

    # Configure root logger minimally
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.WARNING)
    # Clear existing handlers if any
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    root_logger.addHandler(log_handler)

    # Configure pydantic_ai logger
    pydantic_ai_logger = logging.getLogger("pydantic_ai")
    pydantic_ai_logger.setLevel(logging.INFO)
    pydantic_ai_logger.addHandler(log_handler)
    pydantic_ai_logger.propagate = False

    # Configure our application logger (__name__)
    app_module_logger = logging.getLogger(__name__) # Use module name
    app_module_logger.setLevel(logging.DEBUG)
    app_module_logger.addHandler(log_handler)
    app_module_logger.propagate = False # Important to prevent double logging

def main():
    """Entry point: Setup logging and run the app."""
    setup_logging()
    log.info("Starting Textual application.")
    try:
        app = TerminalApp()
        app.run()
        log.info("Application finished.")
    except Exception as e:
        log.exception("Application crashed.")
        print(f"Application crashed: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()