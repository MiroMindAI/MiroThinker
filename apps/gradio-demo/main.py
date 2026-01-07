

Here is the improved code with all emojis removed, maintaining a clean, professional text-based interface.

```python
import asyncio
import json
import logging
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional, TypedDict

import gradio as gr
from dotenv import load_dotenv
from hydra import compose, initialize_config_dir
from omegaconf import DictConfig

# Assuming these are local project imports
from src.config.settings import expose_sub_agents_as_tools
from src.core.pipeline import create_pipeline_components, execute_task_pipeline
from utils import contains_chinese, replace_chinese_punctuation

# ================= Configuration & Logging =================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)
load_dotenv()

# Global Hydra initialization flag
_hydra_initialized = False

# ================= Types & Data Structures =================

class ToolCallData(TypedDict, total=False):
    tool_name: str
    input: Any
    output: Any
    content: str  # Used for show_text/message

class AgentData(TypedDict):
    agent_name: str
    tool_call_order: List[str]
    tools: Dict[str, ToolCallData]

@dataclass
class UIState:
    task_id: Optional[str] = None
    agent_order: List[str] = field(default_factory=list)
    agents: Dict[str, AgentData] = field(default_factory=dict)
    current_agent_id: Optional[str] = None
    errors: List[str] = field(default_factory=list)

# ================= Configuration Loading =================

def load_miroflow_config(config_overrides: Optional[dict] = None) -> DictConfig:
    """Load the full MiroFlow configuration using Hydra."""
    global _hydra_initialized

    miroflow_config_dir = Path(__file__).parent.parent / "miroflow-agent" / "conf"
    if not miroflow_config_dir.exists():
        raise FileNotFoundError(f"MiroFlow config directory not found: {miroflow_config_dir}")

    if not _hydra_initialized:
        try:
            initialize_config_dir(config_dir=str(miroflow_config_dir), version_base=None)
            _hydra_initialized = True
        except Exception as e:
            logger.warning(f"Hydra already initialized or error: {e}")

    overrides = [
        f"llm.provider={os.getenv('DEFAULT_LLM_PROVIDER', 'qwen')}",
        f"llm.model_name={os.getenv('DEFAULT_MODEL_NAME', 'MiroThinker')}",
        f"llm.base_url={os.getenv('BASE_URL', 'http://localhost:11434')}",
        f"agent={os.getenv('DEFAULT_AGENT_SET', 'evaluation')}",
        "benchmark=gaia-validation",
        "+pricing=default",
    ]

    # Map provider names to config files
    provider_map = {"anthropic": "claude", "openai": "openai", "deepseek": "deepseek", "qwen": "qwen-3"}
    if os.getenv("DEFAULT_LLM_PROVIDER") in provider_map:
        overrides[0] = f"llm={provider_map[os.getenv('DEFAULT_LLM_PROVIDER')]}"

    if config_overrides:
        for k, v in config_overrides.items():
            if isinstance(v, dict):
                overrides.extend([f"{k}.{sk}={sv}" for sk, sv in v.items()])
            else:
                overrides.append(f"{k}={v}")

    try:
        return compose(config_name="config", overrides=overrides)
    except Exception as e:
        logger.error(f"Failed to compose Hydra config: {e}")
        raise

# Pre-load resources
cfg = load_miroflow_config(None)
main_agent_tool_manager, sub_agent_tool_managers, output_formatter = create_pipeline_components(cfg)
tool_definitions = asyncio.run(main_agent_tool_manager.get_all_tool_definitions())
tool_definitions += expose_sub_agents_as_tools(cfg.agent.sub_agents)

sub_agent_tool_definitions = {
    name: asyncio.run(mgr.get_all_tool_definitions())
    for name, mgr in sub_agent_tool_managers.items()
}

# ================= Core Logic Classes =================

class ThreadSafeAsyncQueue:
    """Wrapper for asyncio.Queue to handle thread-safe puts."""
    def __init__(self):
        self._queue = asyncio.Queue()
        self._loop = asyncio.get_running_loop()
        self._closed = False

    async def put(self, item: Any):
        if not self._closed:
            await self._queue.put(item)

    def put_nowait_threadsafe(self, item: Any):
        """Schedules a put from a different thread."""
        if self._closed:
            return
        if not self._loop.is_running():
            return
        # We schedule the coroutine on the loop
        asyncio.run_coroutine_threadsafe(self.put(item), self._loop)

    async def get(self) -> Any:
        return await self._queue.get()

    def close(self):
        self._closed = True

class PipelineRunner:
    """Manages the execution of the pipeline in a separate thread."""
    def __init__(self, task_id: str, query: str, queue: ThreadSafeAsyncQueue):
        self.task_id = task_id
        self.query = query
        self.queue = queue
        self.cancel_event = threading.Event()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pipeline")
        self.future = None

    def start(self):
        self.future = self.executor.submit(self._run_pipeline_thread)

    def cancel(self):
        self.cancel_event.set()
        # We don't wait for future result here to allow UI to update immediately

    def _run_pipeline_thread(self):
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            # Wrapper to interface with thread-safe queue
            class QueueProxy:
                async def put(self, item):
                    if self.cancel_event.is_set(): return
                    # Filter before sending to UI
                    self.queue.put_nowait_threadsafe(filter_message(item))

            proxy = QueueProxy()
            proxy.cancel_event = self.cancel_event
            proxy.queue = self.queue

            async def run():
                task = asyncio.create_task(
                    execute_task_pipeline(
                        cfg=cfg, task_id=self.task_id, task_description=self.query,
                        task_file_name=None, main_agent_tool_manager=main_agent_tool_manager,
                        sub_agent_tool_managers=sub_agent_tool_managers,
                        output_formatter=output_formatter, stream_queue=proxy,
                        log_dir=os.getenv("LOG_DIR", "logs/api-server"),
                        tool_definitions=tool_definitions,
                        sub_agent_tool_definitions=sub_agent_tool_definitions,
                    )
                )
                
                # Cancellation watcher
                while not self.cancel_event.is_set():
                    await asyncio.sleep(0.5)
                    if task.done(): break
                
                if self.cancel_event.is_set():
                    task.cancel()
                    try: await task
                    except asyncio.CancelledError: pass

            loop.run_until_complete(run())
        except Exception as e:
            logger.error(f"Pipeline Thread Exception: {e}", exc_info=True)
            self.queue.put_nowait_threadsafe({
                "event": "error", "data": {"error": str(e), "workflow_id": self.task_id}
            })
        finally:
            self.queue.put_nowait_threadsafe(None) # Sentinel for end of stream
            loop.close()

    def cleanup(self):
        if self.future:
            self.future.cancel()
        self.executor.shutdown(wait=False)

# ================= Helper Functions =================

def filter_google_search_organic(organic: List[dict]) -> List[dict]:
    return [{"title": i.get("title", ""), "link": i.get("link", "")} for i in organic]

def filter_message(message: dict) -> dict:
    """Sanitize message data for UI rendering."""
    if message.get("event") != "tool_call":
        return message
    
    data = message.get("data", {})
    tool_name = data.get("tool_name")
    tool_input = data.get("tool_input")

    if not isinstance(tool_input, dict): return message

    # Filter Search Results
    if tool_name == "google_search" and "result" in tool_input:
        try:
            res = json.loads(tool_input["result"])
            if "organic" in res:
                res["organic"] = filter_google_search_organic(res["organic"])
                tool_input["result"] = json.dumps(res, ensure_ascii=False)
        except json.JSONDecodeError: pass

    # Filter Scrape Results
    if tool_name in ["scrape", "scrape_website"] and "result" in tool_input:
        try:
            json.loads(tool_input["result"]) # Check validity
            # If valid JSON, we might want to truncate it or just hide it entirely
            # For now, just clear it to save UI space, or keep if small
            if len(tool_input["result"]) > 5000:
                 tool_input["result"] = tool_input["result"][:5000] + "... [truncated]"
        except json.JSONDecodeError:
             # It's an error text
             tool_input = {"error": tool_input["result"]}
             
    message["data"]["tool_input"] = tool_input
    return message

# ================= UI State Logic =================

def _update_state(state: UIState, message: dict) -> UIState:
    event = message.get("event")
    data = message.get("data", {})

    if event == "start_of_agent":
        agent_id = data.get("agent_id")
        if agent_id:
            state.agents[agent_id] = {
                "agent_name": data.get("agent_name", "Unknown"),
                "tool_call_order": [],
                "tools": {}
            }
            state.agent_order.append(agent_id)
        state.current_agent_id = agent_id

    elif event == "tool_call":
        tool_id = data.get("tool_call_id")
        agent_id = state.current_agent_id or (state.agent_order[-1] if state.agent_order else None)
        
        if agent_id and tool_id:
            if tool_id not in state.agents[agent_id]["tools"]:
                state.agents[agent_id]["tools"][tool_id] = {"tool_name": data.get("tool_name", "unknown")}
                state.agents[agent_id]["tool_call_order"].append(tool_id)
            
            entry = state.agents[agent_id]["tools"][tool_id]
            tool_name = entry["tool_name"]
            
            # Handle text streaming
            if tool_name == "show_text":
                delta = data.get("delta_input", {}).get("text", "")
                full = data.get("tool_input", {}).get("text", "")
                entry["content"] = entry.get("content", "") + delta or full
            
            # Handle I/O
            elif "tool_input" in data:
                inp = data["tool_input"]
                if isinstance(inp, dict) and "result" in inp:
                    entry["output"] = inp
                else:
                    entry["input"] = inp

    elif event == "message":
        # Same as show_text essentially
        msg_id = data.get("message_id")
        agent_id = state.current_agent_id or (state.agent_order[-1] if state.agent_order else None)
        if agent_id and msg_id:
            if msg_id not in state.agents[agent_id]["tools"]:
                state.agents[agent_id]["tools"][msg_id] = {"tool_name": "message"}
                state.agents[agent_id]["tool_call_order"].append(msg_id)
            
            entry = state.agents[agent_id]["tools"][msg_id]
            delta = (data.get("delta") or {}).get("content", "")
            if delta:
                entry["content"] = entry.get("content", "") + delta

    elif event == "error":
        err = data.get("error", str(data))
        state.errors.append(err)

    return state

def _render_markdown(state: UIState) -> str:
    if not state.agent_order and not state.errors:
        return "### System Ready\nWaiting for a task..."

    lines = []
    
    if state.errors:
        lines.append("### Errors")
        for err in state.errors:
            lines.append(f"- `{err}`")
        lines.append("---")

    for idx, agent_id in enumerate(state.agent_order):
        agent = state.agents[agent_id]
        name = agent["agent_name"]
        
        lines.append(f"### Agent: {name}")
        
        for call_id in agent["tool_call_order"]:
            tool = agent["tools"][call_id]
            t_name = tool["tool_name"]
            
            if t_name in ("show_text", "message"):
                content = tool.get("content", "")
                if content:
                    lines.append(f"\n{content}")
            else:
                has_io = "input" in tool or "output" in tool
                if not has_io:
                    lines.append(f"\n*Used `{t_name}`*")
                else:
                    summary = f"[Tool] {t_name}"
                    lines.append(f"\n<details><summary>{summary}</summary>")
                    
                    if "input" in tool:
                        lines.append("**Input:**")
                        lines.append(f"```json\n{json.dumps(tool['input'], ensure_ascii=False, indent=2)}\n```")
                    
                    if "output" in tool:
                        lines.append("**Output:**")
                        out_str = json.dumps(tool['output'], ensure_ascii=False, indent=2)
                        # Truncate huge outputs in UI
                        if len(out_str) > 2000:
                            out_str = out_str[:2000] + "\n... [truncated]"
                        lines.append(f"```json\n{out_str}\n```")
                    
                    lines.append("</details>")
        lines.append("---")
    
    return "\n".join(lines)

# ================= Gradio Interface =================

_CANCEL_FLAGS: Dict[str, bool] = {}
_CANCEL_LOCK = threading.Lock()

def _set_cancel(task_id: str, status: bool):
    with _CANCEL_LOCK:
        _CANCEL_FLAGS[task_id] = status

def _get_cancel(task_id: str) -> bool:
    with _CANCEL_LOCK:
        return _CANCEL_FLAGS.get(task_id, False)

async def gradio_run(query: str, history: list):
    query = replace_chinese_punctuation(query or "")
    if contains_chinese(query):
        yield (
            _render_markdown(UIState(errors=["Chinese input is currently unsupported."])),
            gr.update(interactive=True),
            gr.update(interactive=False),
            history
        )
        return

    task_id = str(uuid.uuid4())
    _set_cancel(task_id, False)
    
    state = UIState(task_id=task_id)
    queue = ThreadSafeAsyncQueue()
    runner = PipelineRunner(task_id, query, queue)
    runner.start()
    
    try:
        # UI Update: Started
        yield (
            _render_markdown(state) + "\n\n*Initializing...*",
            gr.update(interactive=False),
            gr.update(interactive=True),
            history + [[query, None]]
        )

        last_heartbeat = time.time()
        
        while True:
            if _get_cancel(task_id):
                runner.cancel()
                yield (
                    _render_markdown(state) + "\n\n*Stopped by user.*",
                    gr.update(interactive=True),
                    gr.update(interactive=False),
                    history
                )
                break

            try:
                # Wait for message with timeout to allow checking cancel flag
                msg = await asyncio.wait_for(queue.get(), timeout=0.2)
                
                if msg is None:
                    # End of stream
                    yield (
                        _render_markdown(state),
                        gr.update(interactive=True),
                        gr.update(interactive=False),
                        history
                    )
                    break
                
                state = _update_state(state, msg)
                yield (
                    _render_markdown(state),
                    gr.update(interactive=False),
                    gr.update(interactive=True),
                    history
                )
                
                last_heartbeat = time.time()

            except asyncio.TimeoutError:
                if time.time() - last_heartbeat > 30:
                    # Pipeline seems stalled
                    runner.cancel()
                    yield (
                        _render_markdown(state) + "\n\n*Timeout waiting for agent response.*",
                        gr.update(interactive=True),
                        gr.update(interactive=False),
                        history
                    )
                    break
    finally:
        runner.cleanup()
        _set_cancel(task_id, False)

def stop_click(history: list):
    # The actual cancellation is handled in the async generator via flags
    # This just updates buttons immediately to give feedback
    return gr.update(interactive=True), gr.update(interactive=False)

def clear_history():
    return [], None, UIState()

# ================= Main Application =================

def build_demo():
    custom_css = """
    #log-view {
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        padding: 16px;
        background-color: #f9fafb;
        max-height: 600px;
        overflow-y: auto;
        font-family: 'Segoe UI', sans-serif;
    }
    details { margin-bottom: 8px; border: 1px solid #e5e7eb; border-radius: 4px; padding: 4px; }
    summary { cursor: pointer; font-weight: 600; color: #374151; }
    pre { background: #f3f4f6; padding: 8px; border-radius: 4px; overflow-x: auto; }
    """
    
    with gr.Blocks(css=custom_css, title="MiroFlow DeepResearch") as demo:
        gr.Markdown("# MiroFlow DeepResearch")
        gr.Markdown("Multi-agent research pipeline. Enter a query to start the agents.")
        
        with gr.Row():
            with gr.Column(scale=4):
                query_input = gr.Textbox(lines=3, label="Query", placeholder="e.g., What are the latest advancements in fusion energy?")
            with gr.Column(scale=1):
                run_btn = gr.Button("Run", variant="primary", size="lg")
                stop_btn = gr.Button("Stop", variant="stop", interactive=False, size="lg")
        
        with gr.Row():
            clear_btn = gr.Button("Clear History", size="sm")

        with gr.Row():
            # We use a Markdown component to render the logs nicely
            output_log = gr.Markdown(elem_id="log-view", value="### System Ready")

        # State storage (using a simple dict to mimic internal state)
        ui_state = gr.State(value=UIState())
        chat_history = gr.State(value=[])

        # Event bindings
        run_btn.click(
            fn=gradio_run,
            inputs=[query_input, chat_history],
            outputs=[output_log, run_btn, stop_btn, chat_history]
        )
        
        stop_btn.click(
            fn=stop_click,
            inputs=[chat_history],
            outputs=[run_btn, stop_btn]
        ).then( # Then update the log to show stopping
             lambda s: _render_markdown(s) + "\n\n*Stopping...*",
             inputs=[ui_state],
             outputs=[output_log]
        )

        clear_btn.click(
            fn=clear_history,
            outputs=[chat_history, output_log, ui_state]
        )

    return demo

if __name__ == "__main__":
    demo = build_demo()
    demo.queue()
    demo.launch(
        server_name=os.getenv("HOST", "0.0.0.0"),
        server_port=int(os.getenv("PORT", "8000")),
        show_error=True
    )
```
