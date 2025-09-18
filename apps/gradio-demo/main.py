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
from src.config.settings import expose_sub_agents_as_tools
from src.core.pipeline import create_pipeline_components, execute_task_pipeline
from utils import contains_chinese, replace_chinese_punctuation

# Create global cleanup thread pool for operations that won't be affected by asyncio.cancel
cleanup_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="cleanup")

logger = logging.getLogger(__name__)

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
    print("config dir", miroflow_config_dir)

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
    agent_set = os.getenv("DEFAULT_AGENT_SET", "evaluation")  # debug.sh uses evaluation
    openai_base_url = os.getenv("OPENAI_BASE_URL", "http://localhost:11434")
    print("openai_base_url", openai_base_url)

    # Map provider names to config files
    provider_config_map = {
        "anthropic": "claude",
        "openai": "openai",
        "deepseek": "deepseek",
        "qwen": "qwen-3",
    }

    llm_config = provider_config_map.get(
        llm_provider, "qwen-3"
    )  # default changed to qwen-3
    overrides.extend(
        [
            f"llm={llm_config}",
            f"llm.provider={llm_provider}",
            f"llm.model_name={model_name}",
            f"llm.openai_base_url={openai_base_url}",
            f"agent={agent_set}",  # use evaluation instead of default
            "benchmark=gaia-validation",  # refer to debug.sh
            "+pricing=default",
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


# pre load main agent tool definitions to speed up the first request
cfg = load_miroflow_config(None)
# Create pipeline components
main_agent_tool_manager, sub_agent_tool_managers, output_formatter = (
    create_pipeline_components(cfg)
)
tool_definitions = asyncio.run(main_agent_tool_manager.get_all_tool_definitions())
tool_definitions += expose_sub_agents_as_tools(cfg.agent.sub_agents)

# pre load sub agent tool definitions to speed up the first request
sub_agent_tool_definitions = {
    name: asyncio.run(sub_agent_tool_manager.get_all_tool_definitions())
    for name, sub_agent_tool_manager in sub_agent_tool_managers.items()
}


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
        """Put data from other threads"""
        if self._closed or not self._loop:
            return
        self._loop.call_soon_threadsafe(lambda: asyncio.create_task(self.put(item)))

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

            global cfg
            global main_agent_tool_manager
            global sub_agent_tool_managers
            global output_formatter
            global tool_definitions
            global sub_agent_tool_definitions

            async def pipeline_with_cancellation():
                pipeline_task = asyncio.create_task(
                    execute_task_pipeline(
                        cfg=cfg,
                        task_id=workflow_id,
                        task_description=query,
                        task_file_name=None,
                        main_agent_tool_manager=main_agent_tool_manager,
                        sub_agent_tool_managers=sub_agent_tool_managers,
                        output_formatter=output_formatter,
                        stream_queue=wrapper_queue,
                        log_dir=os.getenv("LOG_DIR", "logs/api-server"),
                        tool_definitions=tool_definitions,
                        sub_agent_tool_definitions=sub_agent_tool_definitions,
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


def _append_show_text(tool_entry: dict, delta: str):
    existing = tool_entry.get("content", "")
    tool_entry["content"] = existing + delta


def _is_empty_payload(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        stripped = value.strip()
        return stripped == "" or stripped in ("{}", "[]")
    if isinstance(value, (dict, list, tuple, set)):
        return len(value) == 0
    return False


def _render_markdown(state: dict) -> str:
    lines = []
    emoji_cycle = ["🧠", "🔎", "🛠️", "📚", "🤖", "🧪", "📝", "🧭", "⚙️", "🧮"]
    # Render errors first if any
    if state.get("errors"):
        lines.append("### ❌ Errors")
        for idx, err in enumerate(state["errors"], start=1):
            lines.append(f"- **Error {idx}**: {err}")
        lines.append("\n---\n")
    for idx, agent_id in enumerate(state.get("agent_order", [])):
        agent = state["agents"].get(agent_id, {})
        agent_name = agent.get("agent_name", "unknown")
        emoji = emoji_cycle[idx % len(emoji_cycle)]
        lines.append(f"### {emoji} Agent: {agent_name}")
        for call_id in agent.get("tool_call_order", []):
            call = agent["tools"].get(call_id, {})
            tool_name = call.get("tool_name", "unknown_tool")
            if tool_name in ("show_text", "message"):
                content = call.get("content", "")
                if content:
                    lines.append(content)
            else:
                tool_input = call.get("input")
                tool_output = call.get("output")
                has_input = not _is_empty_payload(tool_input)
                has_output = not _is_empty_payload(tool_output)
                if not has_input and not has_output:
                    # No parameters, only show tool name with emoji on separate line
                    if tool_name == "Partial Summary":
                        lines.append("\n💡Partial Summary\n")
                    else:
                        lines.append(f"\n🔧{tool_name}\n")
                else:
                    # Show as collapsible details for any tool with input or output
                    if tool_name == "Partial Summary":
                        summary = f"💡{tool_name} ({call_id[:8]})"
                    else:
                        summary = f"🔧{tool_name} ({call_id[:8]})"
                    lines.append(f"\n<details><summary>{summary}</summary>")
                    if has_input:
                        pretty = json.dumps(tool_input, ensure_ascii=False, indent=2)
                        lines.append("\n**Input**:\n")
                        lines.append(f"```json\n{pretty}\n```")
                    if has_output:
                        pretty = json.dumps(tool_output, ensure_ascii=False, indent=2)
                        lines.append("\n**Output**:\n")
                        lines.append(f"```json\n{pretty}\n```")
                    lines.append("</details>\n")
        lines.append("\n---\n")
    return "\n".join(lines) if lines else "Waiting..."


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
    if contains_chinese(query):
        yield (
            "we only support English input for the time being.",
            gr.update(interactive=True),
            gr.update(interactive=False),
            ui_state or {"task_id": None},
        )
        return
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
        state = _update_state_with_event(state, message)
        md = _render_markdown(state)
        yield (
            md + _spinner_markup(True),
            gr.update(interactive=False),
            gr.update(interactive=True),
            ui_state,
        )
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
    custom_css = """
    #log-view { border: 1px solid #ececec; padding: 12px; border-radius: 8px; scroll-behavior: smooth; }
    """
    with gr.Blocks(css=custom_css) as demo:
        gr.Markdown("""
        **MiroFlow DeepResearch - Gradio Demo**  
        Enter an English question and observe Agents and tool calls in real time (Markdown + collapsible sections).
        """)
        with gr.Row():
            inp = gr.Textbox(lines=3, label="Question (English only)")
        with gr.Row():
            run_btn = gr.Button("Run")
            stop_btn = gr.Button("Stop", variant="stop", interactive=False)
        out_md = gr.Markdown("", elem_id="log-view")
        ui_state = gr.State({"task_id": None})
        # run: outputs -> markdown, run_btn(update), stop_btn(update), ui_state
        run_btn.click(
            fn=gradio_run,
            inputs=[inp, ui_state],
            outputs=[out_md, run_btn, stop_btn, ui_state],
        )
        # stop: outputs -> run_btn(update), stop_btn(update)
        stop_btn.click(fn=stop_current, inputs=[ui_state], outputs=[run_btn, stop_btn])
    return demo


if __name__ == "__main__":
    demo = build_demo()
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    demo.queue().launch(server_name=host, server_port=port)
