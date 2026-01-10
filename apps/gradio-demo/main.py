import asyncio
import json
import logging
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import AsyncGenerator, List, Optional

import gradio as gr
from dotenv import load_dotenv
from hydra import compose, initialize_config_dir
from omegaconf import DictConfig
from prompt_patch import apply_prompt_patch
from src.config.settings import expose_sub_agents_as_tools
from src.core.pipeline import create_pipeline_components, execute_task_pipeline
from utils import replace_chinese_punctuation

# Apply custom system prompt patch (adds MiroThinker identity)
apply_prompt_patch()

# Create global cleanup thread pool for operations that won't be affected by asyncio.cancel
cleanup_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="cleanup")

logger = logging.getLogger(__name__)

# Set DEMO_MODE for simplified tool configuration
os.environ["DEMO_MODE"] = "1"

# Load environment variables from .env file
load_dotenv()

# Global Hydra initialization flag
_hydra_initialized = False


def load_miroflow_config(config_overrides: Optional[dict] = None) -> DictConfig:
    """
    Load the full MiroFlow configuration using Hydra, similar to how benchmarks work.
    """
    global _hydra_initialized

    # Get the path to the miroflow agent config directory
    miroflow_config_dir = Path(__file__).parent.parent / "miroflow-agent" / "conf"
    miroflow_config_dir = miroflow_config_dir.resolve()
    logger.debug(f"Config dir: {miroflow_config_dir}")

    if not miroflow_config_dir.exists():
        raise FileNotFoundError(
            f"MiroFlow config directory not found: {miroflow_config_dir}"
        )

    # Initialize Hydra if not already done
    if not _hydra_initialized:
        try:
            initialize_config_dir(
                config_dir=str(miroflow_config_dir), version_base=None
            )
            _hydra_initialized = True
        except Exception as e:
            logger.warning(f"Hydra already initialized or error: {e}")

    # Compose configuration with environment variable overrides
    overrides = []

    # Add environment variable based overrides (refer to scripts/debug.sh)
    llm_provider = os.getenv(
        "DEFAULT_LLM_PROVIDER", "qwen"
    )  # debug.sh defaults to qwen
    model_name = os.getenv(
        "DEFAULT_MODEL_NAME", "MiroThinker"
    )  # debug.sh default model
    agent_set = os.getenv("DEFAULT_AGENT_SET", "demo")  # Use demo config
    base_url = os.getenv("BASE_URL", "http://localhost:11434")
    api_key = os.getenv("API_KEY", "")  # API key for LLM endpoint
    logger.debug(f"LLM base_url: {base_url}")

    # Map provider names to config files
    # Available configs: default.yaml, claude-3-7.yaml, gpt-5.yaml, qwen-3.yaml
    provider_config_map = {
        "anthropic": "claude-3-7",
        "openai": "gpt-5",
        "qwen": "qwen-3",
    }

    llm_config = provider_config_map.get(
        llm_provider, "qwen-3"
    )  # fallback to qwen-3 config
    overrides.extend(
        [
            f"llm={llm_config}",
            f"llm.provider={llm_provider}",
            f"llm.model_name={model_name}",
            f"llm.base_url={base_url}",
            f"llm.api_key={api_key}",
            f"agent={agent_set}",
            "agent.main_agent.max_turns=50",  # Limit max turns for gradio demo
            "benchmark=gaia-validation",  # refer to debug.sh
        ]
    )

    # Add config overrides from request
    if config_overrides:
        for key, value in config_overrides.items():
            if isinstance(value, dict):
                for subkey, subvalue in value.items():
                    overrides.append(f"{key}.{subkey}={subvalue}")
            else:
                overrides.append(f"{key}={value}")

    try:
        cfg = compose(config_name="config", overrides=overrides)
        return cfg
    except Exception as e:
        logger.error(f"Failed to compose Hydra config: {e}")
        exit()


# Lazy loading for tool definitions to speed up page load
# Tools will be loaded on first request instead of blocking startup
_preload_cache = {
    "cfg": None,
    "main_agent_tool_manager": None,
    "sub_agent_tool_managers": None,
    "output_formatter": None,
    "tool_definitions": None,
    "sub_agent_tool_definitions": None,
    "loaded": False,
}
_preload_lock = threading.Lock()


def _ensure_preloaded():
    """Lazy load pipeline components on first request."""
    global _preload_cache
    if _preload_cache["loaded"]:
        return

    with _preload_lock:
        if _preload_cache["loaded"]:
            return

        logger.info("Loading pipeline components (first request)...")
        cfg = load_miroflow_config(None)
        main_agent_tool_manager, sub_agent_tool_managers, output_formatter = (
            create_pipeline_components(cfg)
        )
        tool_definitions = asyncio.run(
            main_agent_tool_manager.get_all_tool_definitions()
        )
        if cfg.agent.sub_agents:
            tool_definitions += expose_sub_agents_as_tools(cfg.agent.sub_agents)

        sub_agent_tool_definitions = {
            name: asyncio.run(sub_agent_tool_manager.get_all_tool_definitions())
            for name, sub_agent_tool_manager in sub_agent_tool_managers.items()
        }

        _preload_cache["cfg"] = cfg
        _preload_cache["main_agent_tool_manager"] = main_agent_tool_manager
        _preload_cache["sub_agent_tool_managers"] = sub_agent_tool_managers
        _preload_cache["output_formatter"] = output_formatter
        _preload_cache["tool_definitions"] = tool_definitions
        _preload_cache["sub_agent_tool_definitions"] = sub_agent_tool_definitions
        _preload_cache["loaded"] = True
        logger.info("Pipeline components loaded successfully.")


class ThreadSafeAsyncQueue:
    """Thread-safe async queue wrapper"""

    def __init__(self):
        self._queue = asyncio.Queue()
        self._loop = None
        self._closed = False

    def set_loop(self, loop):
        self._loop = loop

    async def put(self, item):
        """Put data safely from any thread"""
        if self._closed:
            return
        await self._queue.put(item)

    def put_nowait_threadsafe(self, item):
        """Put data from other threads - use direct queue put for lower latency"""
        if self._closed or not self._loop:
            return
        # Use put_nowait directly instead of creating a task for lower latency
        self._loop.call_soon_threadsafe(lambda: self._queue.put_nowait(item))

    async def get(self):
        return await self._queue.get()

    def close(self):
        self._closed = True


def filter_google_search_organic(organic: List[dict]) -> List[dict]:
    """
    Filter google search organic results to remove unnecessary information
    """
    result = []
    for item in organic:
        result.append(
            {
                "title": item.get("title", ""),
                "link": item.get("link", ""),
            }
        )
    return result


def is_scrape_error(result: str) -> bool:
    """
    Check if the scrape result is an error
    """
    try:
        json.loads(result)
        return False
    except json.JSONDecodeError:
        return True


def filter_message(message: dict) -> dict:
    """
    Filter message to remove unnecessary information
    """
    if message["event"] == "tool_call":
        tool_name = message["data"].get("tool_name")
        tool_input = message["data"].get("tool_input")
        if (
            tool_name == "google_search"
            and isinstance(tool_input, dict)
            and "result" in tool_input
        ):
            result_dict = json.loads(tool_input["result"])
            if "organic" in result_dict:
                new_result = {
                    "organic": filter_google_search_organic(result_dict["organic"])
                }
                message["data"]["tool_input"]["result"] = json.dumps(
                    new_result, ensure_ascii=False
                )
        if (
            tool_name in ["scrape", "scrape_website"]
            and isinstance(tool_input, dict)
            and "result" in tool_input
        ):
            # if error, it can not be json
            if is_scrape_error(tool_input["result"]):
                message["data"]["tool_input"] = {"error": tool_input["result"]}
            else:
                message["data"]["tool_input"] = {}
    return message


async def stream_events_optimized(
    task_id: str, query: str, _: Optional[dict] = None, disconnect_check=None
) -> AsyncGenerator[dict, None]:
    """Optimized event stream generator that directly outputs structured events, no longer wrapped as SSE strings."""
    workflow_id = task_id
    last_send_time = time.time()
    last_heartbeat_time = time.time()

    # Create thread-safe queue
    stream_queue = ThreadSafeAsyncQueue()
    stream_queue.set_loop(asyncio.get_event_loop())

    cancel_event = threading.Event()

    def run_pipeline_in_thread():
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            class ThreadQueueWrapper:
                def __init__(self, thread_queue, cancel_event):
                    self.thread_queue = thread_queue
                    self.cancel_event = cancel_event

                async def put(self, item):
                    if self.cancel_event.is_set():
                        logger.info("Pipeline cancelled, stopping execution")
                        return
                    self.thread_queue.put_nowait_threadsafe(filter_message(item))

            wrapper_queue = ThreadQueueWrapper(stream_queue, cancel_event)

            # Ensure pipeline components are loaded (lazy loading)
            _ensure_preloaded()

            async def pipeline_with_cancellation():
                pipeline_task = asyncio.create_task(
                    execute_task_pipeline(
                        cfg=_preload_cache["cfg"],
                        task_id=workflow_id,
                        task_description=query,
                        task_file_name=None,
                        main_agent_tool_manager=_preload_cache[
                            "main_agent_tool_manager"
                        ],
                        sub_agent_tool_managers=_preload_cache[
                            "sub_agent_tool_managers"
                        ],
                        output_formatter=_preload_cache["output_formatter"],
                        stream_queue=wrapper_queue,
                        log_dir=os.getenv("LOG_DIR", "logs/api-server"),
                        tool_definitions=_preload_cache["tool_definitions"],
                        sub_agent_tool_definitions=_preload_cache[
                            "sub_agent_tool_definitions"
                        ],
                    )
                )

                async def check_cancellation():
                    while not cancel_event.is_set():
                        await asyncio.sleep(0.5)
                    logger.info("Cancel event detected, cancelling pipeline")
                    pipeline_task.cancel()

                cancel_task = asyncio.create_task(check_cancellation())

                try:
                    done, pending = await asyncio.wait(
                        [pipeline_task, cancel_task],
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    for task in pending:
                        task.cancel()
                    for task in done:
                        if task == pipeline_task:
                            try:
                                await task
                            except asyncio.CancelledError:
                                logger.info("Pipeline task was cancelled")
                except Exception as e:
                    logger.error(f"Pipeline execution error: {e}")
                    pipeline_task.cancel()
                    cancel_task.cancel()

            loop.run_until_complete(pipeline_with_cancellation())
        except Exception as e:
            if not cancel_event.is_set():
                logger.error(f"Pipeline error: {e}", exc_info=True)
                stream_queue.put_nowait_threadsafe(
                    {
                        "event": "error",
                        "data": {"error": str(e), "workflow_id": workflow_id},
                    }
                )
        finally:
            stream_queue.put_nowait_threadsafe(None)
            if "loop" in locals():
                loop.close()

    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(run_pipeline_in_thread)

    try:
        while True:
            try:
                if disconnect_check and await disconnect_check():
                    logger.info("Client disconnected, stopping pipeline")
                    cancel_event.set()
                    break
                message = await asyncio.wait_for(stream_queue.get(), timeout=0.1)
                if message is None:
                    logger.info("Pipeline completed")
                    break
                yield message
                last_send_time = time.time()
            except asyncio.TimeoutError:
                current_time = time.time()
                if current_time - last_send_time > 300:
                    logger.info("Stream timeout")
                    break
                if future.done():
                    try:
                        message = stream_queue._queue.get_nowait()
                        if message is not None:
                            yield message
                            continue
                    except Exception:
                        break
                if current_time - last_heartbeat_time >= 15:
                    yield {
                        "event": "heartbeat",
                        "data": {"timestamp": current_time, "workflow_id": workflow_id},
                    }
                    last_heartbeat_time = current_time
    except Exception as e:
        logger.error(f"Stream error: {e}", exc_info=True)
        yield {
            "event": "error",
            "data": {"workflow_id": workflow_id, "error": f"Stream error: {str(e)}"},
        }
    finally:
        cancel_event.set()
        stream_queue.close()
        try:
            future.result(timeout=1.0)
        except Exception:
            pass
        executor.shutdown(wait=False)


# ========================= Gradio Integration =========================


def _init_render_state():
    return {
        "agent_order": [],
        "agents": {},  # agent_id -> {"agent_name": str, "tool_call_order": [], "tools": {tool_call_id: {...}}}
        "current_agent_id": None,
        "errors": [],
    }


def _format_think_content(text: str) -> str:
    """Convert <think> tags to readable markdown format."""
    import re

    # Replace <think> tags with blockquote format (no label)
    text = re.sub(r"<think>\s*", "\n> ", text)
    text = re.sub(r"\s*</think>", "\n", text)
    # Convert newlines within thinking to blockquote continuation
    lines = text.split("\n")
    result = []
    in_thinking = False
    for line in lines:
        if line.strip().startswith(">") and not in_thinking:
            in_thinking = True
            result.append(line)
        elif in_thinking and line.strip() and not line.startswith(">"):
            result.append(f"> {line}")
        else:
            if line.strip() == "" and in_thinking:
                in_thinking = False
            result.append(line)
    return "\n".join(result)


def _append_show_text(tool_entry: dict, delta: str):
    existing = tool_entry.get("content", "")
    # Skip "Final boxed answer" content (already shown in main response)
    if "Final boxed answer" in delta:
        return
    # Format think tags for display
    formatted_delta = _format_think_content(delta)
    tool_entry["content"] = existing + formatted_delta


def _is_empty_payload(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        stripped = value.strip()
        return stripped == "" or stripped in ("{}", "[]")
    if isinstance(value, (dict, list, tuple, set)):
        return len(value) == 0
    return False


def _format_search_results(tool_input: dict, tool_output: dict) -> str:
    """Format google_search results in a beautiful card layout."""
    lines = []

    # Get search query from input
    query = ""
    if isinstance(tool_input, dict):
        query = tool_input.get("q", "") or tool_input.get("query", "")

    # Parse results from output - handle multiple formats
    results = []
    if isinstance(tool_output, dict):
        # Case 1: output has "result" field containing JSON string
        result_str = tool_output.get("result", "")
        if isinstance(result_str, str) and result_str.strip():
            try:
                result_data = json.loads(result_str)
                if isinstance(result_data, dict):
                    results = result_data.get("organic", [])
            except json.JSONDecodeError:
                pass
        elif isinstance(result_str, dict):
            results = result_str.get("organic", [])

        # Case 2: output directly contains "organic" field
        if not results and "organic" in tool_output:
            results = tool_output.get("organic", [])

    if not results and not query:
        return ""

    # Build the card
    lines.append('<div class="search-card">')

    # Header with query
    if query:
        lines.append('<div class="search-header">')
        lines.append('<span class="search-icon">🔍</span>')
        lines.append(f'<span class="search-query">Search: "{query}"</span>')
        lines.append("</div>")

    # Results count
    if results:
        lines.append(f'<div class="search-count">≡ Found {len(results)} results</div>')

        # Results list
        lines.append('<div class="search-results">')
        for item in results[:10]:  # Limit to 10 results
            title = item.get("title", "Untitled")
            link = item.get("link", "#")

            lines.append(f"""<a href="{link}" target="_blank" class="search-result-item">
                <span class="result-icon">🌐</span>
                <span class="result-title">{title}</span>
            </a>""")
        lines.append("</div>")

    lines.append("</div>")

    return "\n".join(lines)


def _format_sogou_search_results(tool_input: dict, tool_output: dict) -> str:
    """Format sogou_search results in a beautiful card layout."""
    lines = []

    # Get search query from input
    query = ""
    if isinstance(tool_input, dict):
        query = tool_input.get("q", "") or tool_input.get("query", "")

    # Parse results from output - sogou uses "Pages" instead of "organic"
    results = []
    if isinstance(tool_output, dict):
        result_str = tool_output.get("result", "")
        if isinstance(result_str, str) and result_str.strip():
            try:
                result_data = json.loads(result_str)
                if isinstance(result_data, dict):
                    results = result_data.get("Pages", [])
            except json.JSONDecodeError:
                pass
        elif isinstance(result_str, dict):
            results = result_str.get("Pages", [])

        if not results and "Pages" in tool_output:
            results = tool_output.get("Pages", [])

    if not results and not query:
        return ""

    # Build the card
    lines.append('<div class="search-card">')

    # Header with query
    if query:
        lines.append('<div class="search-header">')
        lines.append('<span class="search-icon">🔍</span>')
        lines.append(f'<span class="search-query">Search: "{query}"</span>')
        lines.append("</div>")

    # Results count
    if results:
        lines.append(f'<div class="search-count">≡ Found {len(results)} results</div>')

        # Results list
        lines.append('<div class="search-results">')
        for item in results[:10]:  # Limit to 10 results
            title = item.get("title", "Untitled")
            link = item.get("url", item.get("link", "#"))

            lines.append(f"""<a href="{link}" target="_blank" class="search-result-item">
                <span class="result-icon">🌐</span>
                <span class="result-title">{title}</span>
            </a>""")
        lines.append("</div>")

    lines.append("</div>")

    return "\n".join(lines)


def _format_scrape_results(tool_input: dict, tool_output: dict) -> str:
    """Format scrape/webpage results in a card layout."""
    lines = []

    # Get URL
    url = ""
    if isinstance(tool_input, dict):
        url = tool_input.get("url", tool_input.get("link", ""))

    # Check for error
    if isinstance(tool_output, dict) and "error" in tool_output:
        lines.append('<div class="scrape-card scrape-error">')
        lines.append('<div class="scrape-header">')
        lines.append('<span class="scrape-icon">🌐</span>')
        lines.append(
            f'<span class="scrape-url">{url[:60]}{"..." if len(url) > 60 else ""}</span>'
        )
        lines.append("</div>")
        lines.append('<div class="scrape-status error">❌ Failed</div>')
        lines.append("</div>")
        return "\n".join(lines)

    # Success case
    lines.append('<div class="scrape-card">')
    if url:
        lines.append('<div class="scrape-header">')
        lines.append('<span class="scrape-icon">🌐</span>')
        lines.append(
            f'<span class="scrape-url">{url[:60]}{"..." if len(url) > 60 else ""}</span>'
        )
        lines.append("</div>")
        lines.append('<div class="scrape-status success">✓ Done</div>')
    lines.append("</div>")

    return "\n".join(lines)


def _render_markdown(state: dict) -> str:
    lines = []
    final_summary_lines = []  # Collect final summary content separately

    # Render errors first if any
    if state.get("errors"):
        for err in state["errors"]:
            lines.append(f'<div class="error-block">❌ {err}</div>')

    # Render all agents' content
    for agent_id in state.get("agent_order", []):
        agent = state["agents"].get(agent_id, {})
        agent_name = agent.get("agent_name", "")
        is_final_summary = agent_name == "Final Summary"

        for call_id in agent.get("tool_call_order", []):
            call = agent["tools"].get(call_id, {})
            tool_name = call.get("tool_name", "unknown_tool")

            # Show text / message - display directly
            if tool_name in ("show_text", "message"):
                content = call.get("content", "")
                if content:
                    if is_final_summary:
                        final_summary_lines.append(content)
                    else:
                        lines.append(content)
                continue

            tool_input = call.get("input", {})
            tool_output = call.get("output", {})
            has_input = not _is_empty_payload(tool_input)
            has_output = not _is_empty_payload(tool_output)

            # Special formatting for google_search
            if tool_name == "google_search" and (has_input or has_output):
                formatted = _format_search_results(tool_input, tool_output)
                if formatted:
                    lines.append(formatted)
                continue

            # Special formatting for sogou_search
            if tool_name == "sogou_search" and (has_input or has_output):
                formatted = _format_sogou_search_results(tool_input, tool_output)
                if formatted:
                    lines.append(formatted)
                continue

            # Special formatting for scrape/webpage tools
            if tool_name in (
                "scrape",
                "scrape_website",
                "scrape_webpage",
                "scrape_and_extract_info",
            ) and (has_input or has_output):
                formatted = _format_scrape_results(tool_input, tool_output)
                if formatted:
                    lines.append(formatted)
                continue

            # Special formatting for code execution tools
            if tool_name in ("python", "run_python_code") and (has_input or has_output):
                # Use pure Markdown to avoid HTML wrapper blocking Markdown rendering
                lines.append("\n---\n")
                lines.append("#### 💻 Code Execution\n")
                # Show code input - try multiple possible keys
                code = ""
                if isinstance(tool_input, dict):
                    code = tool_input.get("code") or tool_input.get("code_block") or ""
                elif isinstance(tool_input, str):
                    code = tool_input
                if code:
                    lines.append(f"\n```python\n{code}\n```\n")
                # Show output if available
                if has_output:
                    output = ""
                    if isinstance(tool_output, dict):
                        output = (
                            tool_output.get("result")
                            or tool_output.get("output")
                            or tool_output.get("stdout")
                            or ""
                        )
                    elif isinstance(tool_output, str):
                        output = tool_output
                    if isinstance(output, str) and output.strip():
                        lines.append("\n**Output:**\n")
                        lines.append(
                            f'\n```text\n{output[:1000]}{"..." if len(output) > 1000 else ""}\n```\n'
                        )
                lines.append("\n✅ Executed\n")
                continue

            # Other tools - show as compact card
            if has_input or has_output:
                target_lines = final_summary_lines if is_final_summary else lines
                target_lines.append('<div class="tool-card">')
                target_lines.append(f'<div class="tool-header">🔧 {tool_name}</div>')
                if has_input:
                    # Show brief input summary
                    if isinstance(tool_input, dict):
                        brief = ", ".join(
                            f"{k}: {str(v)[:30]}..."
                            if len(str(v)) > 30
                            else f"{k}: {v}"
                            for k, v in list(tool_input.items())[:2]
                        )
                        target_lines.append(f'<div class="tool-brief">{brief}</div>')
                if has_output:
                    target_lines.append('<div class="tool-status">✓ Done</div>')
                target_lines.append("</div>")

    # Add final summary with Markdown-based styling (no HTML wrapper to preserve Markdown rendering)
    if final_summary_lines:
        lines.append("\n\n---\n\n")  # Markdown horizontal rule as divider
        lines.append("## 📋 Research Summary\n\n")
        lines.extend(final_summary_lines)

    return "\n".join(lines) if lines else "*Waiting to start research...*"


def _update_state_with_event(state: dict, message: dict):
    event = message.get("event")
    data = message.get("data", {})
    if event == "start_of_agent":
        agent_id = data.get("agent_id")
        agent_name = data.get("agent_name", "unknown")
        if agent_id and agent_id not in state["agents"]:
            state["agents"][agent_id] = {
                "agent_name": agent_name,
                "tool_call_order": [],
                "tools": {},
            }
            state["agent_order"].append(agent_id)
        state["current_agent_id"] = agent_id
    elif event == "end_of_agent":
        # End marker, no special handling needed, keep structure
        state["current_agent_id"] = None
    elif event == "tool_call":
        tool_call_id = data.get("tool_call_id")
        tool_name = data.get("tool_name", "unknown_tool")
        agent_id = state.get("current_agent_id") or (
            state["agent_order"][-1] if state["agent_order"] else None
        )
        if not agent_id:
            return state
        agent = state["agents"].setdefault(
            agent_id, {"agent_name": "unknown", "tool_call_order": [], "tools": {}}
        )
        tools = agent["tools"]
        if tool_call_id not in tools:
            tools[tool_call_id] = {"tool_name": tool_name}
            agent["tool_call_order"].append(tool_call_id)
        entry = tools[tool_call_id]
        if tool_name == "show_text" and "delta_input" in data:
            delta = data.get("delta_input", {}).get("text", "")
            _append_show_text(entry, delta)
        elif tool_name == "show_text" and "tool_input" in data:
            ti = data.get("tool_input")
            text = ""
            if isinstance(ti, dict):
                text = ti.get("text", "") or (
                    (ti.get("result") or {}).get("text")
                    if isinstance(ti.get("result"), dict)
                    else ""
                )
            elif isinstance(ti, str):
                text = ti
            if text:
                _append_show_text(entry, text)
        else:
            # Distinguish between input and output:
            if "tool_input" in data:
                # Could be input (first time) or output with result (second time)
                ti = data["tool_input"]
                # If contains result, assign to output; otherwise assign to input
                if isinstance(ti, dict) and "result" in ti:
                    entry["output"] = ti
                else:
                    # Only update input if we don't already have valid input data, or if the new data is not empty
                    if "input" not in entry or not _is_empty_payload(ti):
                        entry["input"] = ti
    elif event == "message":
        # Same incremental text display as show_text, aggregated by message_id
        message_id = data.get("message_id")
        agent_id = state.get("current_agent_id") or (
            state["agent_order"][-1] if state["agent_order"] else None
        )
        if not agent_id:
            return state
        agent = state["agents"].setdefault(
            agent_id, {"agent_name": "unknown", "tool_call_order": [], "tools": {}}
        )
        tools = agent["tools"]
        if message_id not in tools:
            tools[message_id] = {"tool_name": "message"}
            agent["tool_call_order"].append(message_id)
        entry = tools[message_id]
        delta_content = (data.get("delta") or {}).get("content", "")
        if isinstance(delta_content, str) and delta_content:
            _append_show_text(entry, delta_content)
    elif event == "error":
        # Collect errors, display uniformly during rendering
        err_text = data.get("error") if isinstance(data, dict) else None
        if not err_text:
            try:
                err_text = json.dumps(data, ensure_ascii=False)
            except Exception:
                err_text = str(data)
        state.setdefault("errors", []).append(err_text)
    else:
        # Ignore heartbeat or other events
        pass

    return state


_CANCEL_FLAGS = {}
_CANCEL_LOCK = threading.Lock()


def _set_cancel_flag(task_id: str):
    with _CANCEL_LOCK:
        _CANCEL_FLAGS[task_id] = True


def _reset_cancel_flag(task_id: str):
    with _CANCEL_LOCK:
        _CANCEL_FLAGS[task_id] = False


async def _disconnect_check_for_task(task_id: str):
    with _CANCEL_LOCK:
        return _CANCEL_FLAGS.get(task_id, False)


def _spinner_markup(running: bool) -> str:
    if not running:
        return ""
    return (
        '\n\n<div style="display:flex;align-items:center;gap:8px;color:#555;margin-top:8px;">'
        '<div style="width:16px;height:16px;border:2px solid #ddd;border-top-color:#3b82f6;border-radius:50%;animation:spin 0.8s linear infinite;"></div>'
        "<span>Generating...</span>"
        "</div>\n<style>@keyframes spin{to{transform:rotate(360deg)}}</style>\n"
    )


async def gradio_run(query: str, ui_state: Optional[dict]):
    query = replace_chinese_punctuation(query or "")
    task_id = str(uuid.uuid4())
    _reset_cancel_flag(task_id)
    if not ui_state:
        ui_state = {"task_id": task_id}
    else:
        ui_state = {**ui_state, "task_id": task_id}
    state = _init_render_state()
    # Initial: disable Run, enable Stop, and show spinner at bottom of text
    yield (
        _render_markdown(state) + _spinner_markup(True),
        gr.update(interactive=False),
        gr.update(interactive=True),
        ui_state,
    )
    async for message in stream_events_optimized(
        task_id, query, None, lambda: _disconnect_check_for_task(task_id)
    ):
        # Skip heartbeat events - they don't need UI update
        event_type = message.get("event", "unknown")
        if event_type == "heartbeat":
            continue

        state = _update_state_with_event(state, message)
        md = _render_markdown(state)
        yield (
            md + _spinner_markup(True),
            gr.update(interactive=False),
            gr.update(interactive=True),
            ui_state,
        )
        # Small delay to allow Gradio to process the update
        await asyncio.sleep(0.01)
    # End: enable Run, disable Stop, remove spinner
    yield (
        _render_markdown(state),
        gr.update(interactive=True),
        gr.update(interactive=False),
        ui_state,
    )


def stop_current(ui_state: Optional[dict]):
    tid = (ui_state or {}).get("task_id")
    if tid:
        _set_cancel_flag(tid)
    # Immediately switch button availability: enable Run, disable Stop
    return (
        gr.update(interactive=True),
        gr.update(interactive=False),
    )


def build_demo():
    # Use remote logo from dr.miromind.ai for faster page load

    custom_css = """
    /* ========== MiroThinker - Modern Clean Design ========== */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    
    /* Base */
    .gradio-container {
        max-width: 100% !important;
        margin: 0 !important;
        padding: 0 !important;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
        background: #ffffff !important;
        min-height: 100vh;
    }
    
    footer { display: none !important; }
    
    /* ===== Top Navigation ===== */
    .top-nav {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 16px 32px;
        border-bottom: 1px solid #f0f0f0;
        background: #ffffff;
    }
    
    .nav-left {
        display: flex;
        align-items: center;
        gap: 20px;
    }
    
    .nav-brand {
        display: flex;
        align-items: center;
        gap: 10px;
        font-weight: 600;
        font-size: 1.1em;
        color: #18181b;
    }
    
    .brand-logo {
        width: 32px;
        height: 32px;
        border-radius: 6px;
    }
    
    .nav-links {
        display: flex;
        align-items: center;
        gap: 12px;
    }
    
    .nav-links a {
        color: #71717a;
        font-size: 1.1em;
        text-decoration: none;
        transition: color 0.2s;
    }
    
    .nav-links a:hover {
        color: #18181b;
    }
    
    .nav-right {
        display: flex;
        align-items: center;
        gap: 16px;
    }
    
    .nav-right a {
        color: #52525b;
        text-decoration: none;
        font-size: 0.9em;
    }
    
    /* ===== Hero Section ===== */
    .hero-section {
        text-align: center;
        padding: 60px 24px 40px;
        max-width: 900px;
        margin: 0 auto;
    }
    
    .hero-title {
        font-size: 3em;
        font-weight: 700;
        background: linear-gradient(135deg, #10b981 0%, #14b8a6 50%, #06b6d4 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        margin: 0 0 16px 0;
        letter-spacing: -0.02em;
    }
    
    .hero-subtitle {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 16px;
        color: #71717a;
        font-size: 1em;
    }
    
    .hero-line {
        width: 40px;
        height: 1px;
        background: #d4d4d8;
    }
    
    /* ===== Input Section ===== */
    #input-section {
        max-width: 720px !important;
        margin: 0 auto 40px !important;
        background: #ffffff;
        border: 1px solid #e0e0e0;
        border-radius: 16px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.04);
    }
    
    #question-input {
        padding: 20px 24px !important;
        background: #ffffff !important;
        border: none !important;
    }
    
    #question-input textarea {
        background: #ffffff !important;
        border: none !important;
        font-size: 1.05em !important;
        line-height: 1.7 !important;
        color: #18181b !important;
        box-shadow: none !important;
    }
    
    #question-input textarea:focus {
        outline: none !important;
        box-shadow: none !important;
    }
    
    #question-input textarea::placeholder {
        color: #9ca3af !important;
    }
    
    #btn-row {
        padding: 16px 24px !important;
        border-top: 1px solid #f0f0f0;
        gap: 12px !important;
    }
    
    #run-btn {
        background: linear-gradient(135deg, #10b981 0%, #14b8a6 100%) !important;
        color: #ffffff !important;
        border: none !important;
        border-radius: 10px !important;
        padding: 12px 24px !important;
        font-size: 0.95em !important;
        font-weight: 500 !important;
        cursor: pointer !important;
        transition: opacity 0.2s, transform 0.2s !important;
    }
    
    #run-btn:hover {
        opacity: 0.9 !important;
        transform: translateY(-1px) !important;
    }
    
    #stop-btn {
        background: #ffffff !important;
        color: #71717a !important;
        border: 1px solid #e5e5e5 !important;
        border-radius: 10px !important;
        padding: 12px 20px !important;
        font-size: 0.95em !important;
        font-weight: 500 !important;
        cursor: pointer !important;
        transition: all 0.2s !important;
    }
    
    #stop-btn:hover {
        color: #ef4444 !important;
        border-color: #fecaca !important;
        background: #fef2f2 !important;
    }
    
    /* ===== Output Section ===== */
    #output-section {
        max-width: 900px !important;
        margin: 0 auto !important;
        padding: 0 24px 60px !important;
    }
    
    .output-label {
        font-size: 0.85em;
        font-weight: 500;
        color: #71717a;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 12px;
        padding: 0 4px;
    }
    
    #log-view {
        padding: 24px !important;
        min-height: 400px;
        max-height: 70vh;
        overflow-y: auto;
        background: #ffffff !important;
        border: 1px solid #e5e5e5 !important;
        border-radius: 16px !important;
    }
    
    #log-view h3 {
        font-size: 0.95em;
        font-weight: 600;
        color: #18181b;
        margin: 24px 0 16px 0;
        padding-bottom: 8px;
        border-bottom: 1px solid #f4f4f5;
    }
    
    #log-view h3:first-child {
        margin-top: 0;
    }
    
    /* Error block */
    .error-block {
        background: #fef2f2;
        border: 1px solid #fecaca;
        border-radius: 10px;
        padding: 12px 16px;
        margin: 12px 0;
        color: #dc2626;
        font-size: 0.9em;
    }
    
    /* Tool card */
    .tool-card {
        background: #fafafa;
        border: 1px solid #e5e5e5;
        border-radius: 10px;
        padding: 12px 16px;
        margin: 12px 0;
    }
    
    .tool-header {
        font-size: 0.9em;
        font-weight: 500;
        color: #3f3f46;
        margin-bottom: 4px;
    }
    
    .tool-brief {
        font-size: 0.8em;
        color: #71717a;
        margin-top: 4px;
    }
    
    .tool-status {
        font-size: 0.8em;
        color: #10b981;
        margin-top: 6px;
    }
    
    #log-view blockquote {
        background: linear-gradient(135deg, #f0fdf4 0%, #ecfeff 100%);
        border: none;
        border-left: 3px solid #10b981;
        padding: 16px 20px;
        margin: 16px 0;
        border-radius: 0 12px 12px 0;
        font-style: normal;
        color: #065f46;
        font-size: 0.9em;
        line-height: 1.7;
    }
    
    #log-view pre {
        background: #f8f9fa !important;
        color: #1e293b !important;
        border-radius: 8px !important;
        padding: 16px !important;
        font-size: 0.85em !important;
        line-height: 1.6 !important;
        overflow-x: auto;
        margin: 12px 0;
        border: 1px solid #e2e8f0;
    }
    
    #log-view pre code {
        background: transparent !important;
        color: #1e293b !important;
        font-family: 'SF Mono', 'Fira Code', 'JetBrains Mono', Consolas, monospace !important;
        font-size: inherit !important;
        padding: 0 !important;
        white-space: pre-wrap;
        word-break: break-word;
    }
    
    #log-view code {
        font-family: 'SF Mono', 'Fira Code', 'JetBrains Mono', Consolas, monospace !important;
        background: #f1f5f9 !important;
        color: #1e293b !important;
        padding: 2px 6px !important;
        border-radius: 4px !important;
        font-size: 0.9em !important;
    }
    
    #log-view p {
        line-height: 1.7;
        color: #3f3f46;
    }
    
    #log-view::-webkit-scrollbar {
        width: 6px;
    }
    
    #log-view::-webkit-scrollbar-track {
        background: transparent;
    }
    
    #log-view::-webkit-scrollbar-thumb {
        background: #e5e5e5;
        border-radius: 3px;
    }
    
    #log-view::-webkit-scrollbar-thumb:hover {
        background: #d4d4d8;
    }
    
    /* ===== Footer ===== */
    .app-footer {
        text-align: center;
        padding: 24px;
        color: #a1a1aa;
        font-size: 0.85em;
        border-top: 1px solid #f0f0f0;
    }
    
    /* ===== Loading Spinner ===== */
    @keyframes spin {
        to { transform: rotate(360deg); }
    }
    
    .loading-indicator {
        display: inline-flex;
        align-items: center;
        gap: 10px;
        color: #10b981;
        font-size: 0.9em;
        padding: 12px 0;
    }
    
    .loading-indicator::before {
        content: '';
        width: 16px;
        height: 16px;
        border: 2px solid #d1fae5;
        border-top-color: #10b981;
        border-radius: 50%;
        animation: spin 0.8s linear infinite;
    }
    
    /* ===== Search Results Card ===== */
    .search-card {
        background: #ffffff;
        border: 1px solid #e5e5e5;
        border-radius: 12px;
        margin: 16px 0;
        overflow: hidden;
    }
    
    .search-header {
        display: flex;
        align-items: center;
        gap: 10px;
        padding: 14px 18px;
        background: #fafafa;
        border-bottom: 1px solid #f0f0f0;
    }
    
    .search-icon {
        font-size: 1em;
        color: #10b981;
    }
    
    .search-query {
        font-size: 0.9em;
        color: #3f3f46;
        font-weight: 500;
    }
    
    .search-count {
        padding: 10px 18px;
        font-size: 0.8em;
        color: #71717a;
        background: #fafafa;
        border-bottom: 1px solid #f0f0f0;
    }
    
    .search-results {
        padding: 8px 0;
    }
    
    .search-result-item {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 12px 18px;
        text-decoration: none;
        color: #3f3f46;
        font-size: 0.9em;
        transition: background 0.15s;
        border-left: 3px solid transparent;
    }
    
    .search-result-item:hover {
        background: #f9fafb;
        border-left-color: #10b981;
    }
    
    .result-icon {
        font-size: 1em;
        flex-shrink: 0;
        opacity: 0.6;
    }
    
    .result-title {
        flex: 1;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }
    
    /* ===== Scrape Card ===== */
    .scrape-card {
        background: #ffffff;
        border: 1px solid #e5e5e5;
        border-radius: 10px;
        margin: 12px 0;
        padding: 12px 16px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
    }
    
    .scrape-card.scrape-error {
        border-color: #fecaca;
        background: #fef2f2;
    }
    
    .scrape-header {
        display: flex;
        align-items: center;
        gap: 10px;
        flex: 1;
        min-width: 0;
    }
    
    .scrape-icon {
        font-size: 1em;
        opacity: 0.6;
    }
    
    .scrape-url {
        font-size: 0.85em;
        color: #52525b;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }
    
    .scrape-status {
        font-size: 0.8em;
        padding: 4px 10px;
        border-radius: 6px;
        flex-shrink: 0;
    }
    
    .scrape-status.success {
        background: #ecfdf5;
        color: #059669;
    }
    
    .scrape-status.error {
        background: #fef2f2;
        color: #dc2626;
    }
    
    /* ===== Final Summary Section ===== */
    .final-summary-divider {
        height: 1px;
        background: linear-gradient(to right, transparent, #e5e5e5, transparent);
        margin: 32px 0;
    }
    
    .final-summary-section {
        background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
        border: 1px solid #e2e8f0;
        border-radius: 16px;
        padding: 24px;
        margin-top: 16px;
    }
    
    .final-summary-header {
        font-size: 1.1em;
        font-weight: 600;
        color: #1e293b;
        margin-bottom: 16px;
        padding-bottom: 12px;
        border-bottom: 2px solid #3b82f6;
        display: inline-block;
    }
    
    .final-summary-content {
        color: #334155;
        line-height: 1.8;
    }
    
    .final-summary-content h1,
    .final-summary-content h2,
    .final-summary-content h3 {
        color: #1e293b;
        margin-top: 1.5em;
        margin-bottom: 0.5em;
    }
    
    .final-summary-content h1 { font-size: 1.4em; }
    .final-summary-content h2 { font-size: 1.2em; }
    .final-summary-content h3 { font-size: 1.1em; }
    
    .final-summary-content p {
        margin: 0.8em 0;
    }
    
    .final-summary-content ul,
    .final-summary-content ol {
        margin: 0.8em 0;
        padding-left: 1.5em;
    }
    
    .final-summary-content li {
        margin: 0.4em 0;
    }
    
    .final-summary-content a {
        color: #3b82f6;
        text-decoration: none;
    }
    
    .final-summary-content a:hover {
        text-decoration: underline;
    }
    
    .final-summary-content code {
        background: #e2e8f0;
        padding: 2px 6px;
        border-radius: 4px;
        font-family: 'SF Mono', 'Fira Code', monospace;
        font-size: 0.9em;
    }
    
    .final-summary-content pre {
        background: #1e293b;
        color: #e2e8f0;
        padding: 16px;
        border-radius: 8px;
        overflow-x: auto;
    }
    
    .final-summary-content pre code {
        background: transparent;
        padding: 0;
        color: inherit;
    }
    
    .final-summary-content table {
        width: 100%;
        border-collapse: collapse;
        margin: 1em 0;
    }
    
    .final-summary-content th,
    .final-summary-content td {
        padding: 10px 12px;
        border: 1px solid #e2e8f0;
        text-align: left;
    }
    
    .final-summary-content th {
        background: #f1f5f9;
        font-weight: 600;
    }
    
    .final-summary-content blockquote {
        border-left: 4px solid #3b82f6;
        margin: 1em 0;
        padding: 0.5em 1em;
        background: #f8fafc;
        color: #475569;
    }
    
    /* ===== Code Execution Card ===== */
    .code-card {
        background: #1e1e2e;
        border: 1px solid #313244;
        border-radius: 12px;
        margin: 12px 0;
        padding: 16px;
        overflow: hidden;
    }
    
    .code-header {
        font-size: 0.9em;
        font-weight: 600;
        color: #cdd6f4;
        margin-bottom: 12px;
        display: flex;
        align-items: center;
        gap: 8px;
    }
    
    .code-card pre {
        background: #11111b !important;
        border-radius: 8px;
        padding: 12px 16px;
        margin: 8px 0;
        overflow-x: auto;
        font-family: 'SF Mono', 'Fira Code', 'JetBrains Mono', Consolas, monospace !important;
        font-size: 0.85em;
        line-height: 1.5;
    }
    
    .code-card code {
        background: transparent !important;
        color: #cdd6f4 !important;
        font-family: 'SF Mono', 'Fira Code', 'JetBrains Mono', Consolas, monospace !important;
    }
    
    .code-output-label {
        font-size: 0.8em;
        color: #a6adc8;
        margin-top: 12px;
        margin-bottom: 4px;
    }
    
    .code-status {
        font-size: 0.8em;
        color: #a6e3a1;
        margin-top: 8px;
        text-align: right;
    }
    
    /* ===== Responsive ===== */
    @media (max-width: 768px) {
        .hero-title {
            font-size: 2em;
        }
        
        .hero-section {
            padding: 40px 16px 24px;
        }
        
        .input-wrapper, .output-wrapper {
            padding: 0 16px;
        }
        
        #log-view {
            max-height: 50vh;
        }
    }
    """

    # Favicon head content
    favicon_head = '<link rel="icon" href="https://dr.miromind.ai/favicon.ico?v=2">'

    with gr.Blocks(
        css=custom_css,
        title="MiroThinker - Deep Research",
        theme=gr.themes.Base(),
        head=favicon_head,
    ) as demo:
        # Top Navigation
        gr.HTML("""
            <nav class="top-nav">
                <div class="nav-left">
                    <div class="nav-brand">
                        <img src="https://dr.miromind.ai/favicon.png" class="brand-logo" alt="MiroThinker" />
                        MiroThinker
                    </div>
                    <div class="nav-links">
                        <a href="https://huggingface.co/MiroMind" target="_blank">🤗</a>
                        <a href="https://github.com/MiroMind/MiroThinker" target="_blank">
                            <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                                <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/>
                            </svg>
                        </a>
                    </div>
                </div>
                <div class="nav-right">
                    <a href="https://miromind.ai" target="_blank">Visit Website</a>
                </div>
            </nav>
        """)

        # Hero Section
        gr.HTML("""
            <div class="hero-section">
                <h1 class="hero-title">Research Deep. Uncover the Future</h1>
                <div class="hero-subtitle">
                    <span class="hero-line"></span>
                    Don't just chat. Predict, verify, and discover with science-based AI.
                    <span class="hero-line"></span>
                </div>
            </div>
        """)

        # Input Section
        with gr.Column(elem_id="input-section"):
            inp = gr.Textbox(
                lines=4,
                placeholder="Enter your research question...",
                show_label=False,
                elem_id="question-input",
            )
            with gr.Row(elem_id="btn-row"):
                stop_btn = gr.Button(
                    "⏹ Stop",
                    elem_id="stop-btn",
                    variant="stop",
                    interactive=False,
                    scale=1,
                )
                run_btn = gr.Button(
                    "Start Research ➤", elem_id="run-btn", variant="primary", scale=2
                )

        # Output Section
        with gr.Column(elem_id="output-section"):
            gr.HTML('<div class="output-label">Research Progress</div>')
            out_md = gr.Markdown("*Waiting to start research...*", elem_id="log-view")

        # State
        ui_state = gr.State({"task_id": None})

        # Event handlers
        run_btn.click(
            fn=gradio_run,
            inputs=[inp, ui_state],
            outputs=[out_md, run_btn, stop_btn, ui_state],
        )
        stop_btn.click(fn=stop_current, inputs=[ui_state], outputs=[run_btn, stop_btn])

        # Footer
        gr.HTML("""
            <div class="app-footer">
                Content generated by MiroMind AI. Please verify important information.
            </div>
        """)

    return demo


if __name__ == "__main__":
    demo = build_demo()
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8080"))
    demo.queue().launch(server_name=host, server_port=port)
