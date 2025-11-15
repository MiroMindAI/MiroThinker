# Copyright (c) 2025 MiroMind
# This source code is licensed under the MIT License.

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

# Import colorama for cross-platform colored output
from colorama import Fore, Style, init

# Initialize colorama
init(autoreset=True, strip=False)

# This will be set to the configured logger instance
logger = None


def get_color_for_level(level: str) -> str:
    """Get color code based on log level for better visual distinction"""
    if level == "ERROR":
        return f"{Fore.RED}{Style.BRIGHT}"
    elif level == "WARNING":
        return f"{Fore.YELLOW}{Style.BRIGHT}"
    elif level == "INFO":
        return f"{Fore.GREEN}{Style.BRIGHT}"
    elif level == "DEBUG":
        return f"{Fore.CYAN}{Style.BRIGHT}"
    else:
        return f"{Fore.WHITE}{Style.BRIGHT}"


class ColoredFormatter(logging.Formatter):
    """Custom formatter that adds colors for better developer visualization"""

    def format(self, record):
        # Get timestamp and format it
        timestamp = self.formatTime(record, self.datefmt)

        # Color the level name based on severity
        level_color = get_color_for_level(record.levelname)
        level_reset = Style.RESET_ALL

        # Color the logger name (miroflow_agent)
        name_color = f"{Fore.BLUE}{Style.BRIGHT}"
        name_reset = Style.RESET_ALL

        # Get the message as is (icons are already added in log_step)
        message = record.getMessage()

        # Format with selective coloring
        formatted = f"[{timestamp}][{name_color}{record.name}{name_reset}][{level_color}{record.levelname}{level_reset}] - {message}"

        return formatted


def bootstrap_logger() -> logging.Logger:
    """Configure the miroflow_agent logger with consistent formatting"""

    global logger

    # Configure miroflow_agent logger
    miroflow_agent_logger = logging.getLogger("miroflow_agent")

    # Check if logger already has handlers to prevent duplicate configuration
    if miroflow_agent_logger.handlers:
        logger = miroflow_agent_logger
        return miroflow_agent_logger

    # Create formatter with consistent format
    formatter = ColoredFormatter(
        "%(asctime)s,%(msecs)03d",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Add our handler with the specified formatter
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    miroflow_agent_logger.addHandler(handler)
    miroflow_agent_logger.setLevel(logging.DEBUG)

    # Disable propagation to prevent duplicate logging from root logger
    miroflow_agent_logger.propagate = False

    # Set the global logger variable
    logger = miroflow_agent_logger

    return miroflow_agent_logger


def get_utc_plus_8_time() -> str:
    """Get UTC+8 timezone current time string"""
    utc_plus_8 = timezone(timedelta(hours=8))
    return datetime.now(utc_plus_8).strftime("%Y-%m-%d %H:%M:%S")


@dataclass
class LLMCallLog:
    """Record technical details of LLM calls"""

    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0
    error: Optional[str] = None


@dataclass
class ToolCallLog:
    """Record detailed information of tool calls"""

    server_name: str
    tool_name: str
    arguments: Dict[str, Any] = field(default_factory=dict)
    result: Any = None
    error: Optional[str] = None
    call_time: Optional[str] = None


@dataclass
class StepLog:
    """Record detailed information of task execution steps"""

    step_name: str
    message: str
    timestamp: str
    info_level: Literal["info", "warning", "error", "debug"] = "info"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validate info_level after initialization"""
        valid_levels = {"info", "warning", "error", "debug"}
        if self.info_level not in valid_levels:
            raise ValueError(
                f"info_level must be one of {valid_levels}, got '{self.info_level}'"
            )


@dataclass
class TaskLog:
    status: str = "running"
    start_time: str = ""
    end_time: str = ""

    task_id: str = ""
    input: Any = None
    ground_truth: str = ""
    final_boxed_answer: str = ""
    final_judge_result: str = ""
    judge_type: str = ""
    error: str = ""

    # Main records: main agent conversation turns
    current_main_turn_id: int = 0
    current_sub_agent_turn_id: int = 0
    sub_agent_counter: int = 0
    current_sub_agent_session_id: Optional[str] = None

    env_info: Optional[dict] = field(default_factory=dict)
    log_dir: str = "logs"

    main_agent_message_history: List[Dict[str, Any]] = field(default_factory=list)
    sub_agent_message_history_sessions: Dict[str, List[Dict[str, Any]]] = field(
        default_factory=dict
    )

    step_logs: List[StepLog] = field(default_factory=list)
    trace_data: Dict[str, Any] = field(default_factory=dict)

    def start_sub_agent_session(
        self, sub_agent_name: str, subtask_description: str
    ) -> str:
        """Start a new sub-agent session"""
        self.sub_agent_counter += 1
        session_id = f"{sub_agent_name}_{self.sub_agent_counter}"
        self.current_sub_agent_session_id = session_id

        # Record sub-agent session start
        self.log_step(
            "info",
            f"{sub_agent_name} | Session Start",
            f"Starting {session_id} for subtask: {subtask_description[:100]}{'...' if len(subtask_description) > 100 else ''}",
            metadata={"session_id": session_id, "subtask": subtask_description},
        )

        return session_id

    def end_sub_agent_session(self, sub_agent_name: str) -> Optional[str]:
        """End the current sub-agent session"""
        self.log_step(
            "info",
            f"{sub_agent_name} | Session End",
            f"Ending {self.current_sub_agent_session_id}",
            metadata={"session_id": self.current_sub_agent_session_id},
        )
        self.current_sub_agent_session_id = None
        return None

    def log_step(
        self,
        info_level: Literal["info", "warning", "error", "debug"],
        step_name: str,
        message: str,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """Record execution step"""
        # Add icons to step_name based on content
        icon = ""
        if "Tool Call Start" in step_name:
            icon = "▶️ "
        elif "Tool Call Success" in step_name:
            icon = "✅ "
        elif "Tool Call Error" in step_name or (
            "error" in info_level and "tool" in step_name.lower()
        ):
            icon = "❌ "
        elif "agent-" in step_name:
            icon = "🤖 "
        elif "Main Agent" in step_name:
            icon = "👑 "
        elif "LLM" in step_name:
            icon = "🧠 "
        elif "ToolManager" in step_name or "Tool Call" in step_name:
            icon = "🔧 "
        elif "tool-python" in step_name.lower():
            icon = "🐍 "
        elif "tool-google-search" in step_name.lower():
            icon = "🔍 "
        elif "tool-browser" in step_name.lower() or "playwright" in step_name.lower():
            icon = "🌐 "

        # Add icon to step_name
        step_name_with_icon = f"{icon}{step_name}"

        step_log = StepLog(
            step_name=step_name_with_icon,
            message=message,
            timestamp=get_utc_plus_8_time(),
            info_level=info_level,
            metadata=metadata or {},
        )

        self.step_logs.append(step_log)

        # Print the structured log to console using the configured logger
        log_message = f"{step_name_with_icon}: {message}"

        # Ensure logger is configured
        global logger
        if logger is None:
            logger = bootstrap_logger()

        if info_level == "error":
            logger.error(log_message)
        elif info_level == "warning":
            logger.warning(log_message)
        elif info_level == "debug":
            logger.debug(log_message)
        else:  # info
            logger.info(log_message)

    def serialize_for_json(self, obj):
        """Convert objects to JSON-serializable format"""
        if isinstance(obj, Path):
            return str(obj)
        elif isinstance(obj, dict):
            return {k: self.serialize_for_json(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self.serialize_for_json(item) for item in obj]
        elif hasattr(obj, "__dict__"):
            return self.serialize_for_json(obj.__dict__)
        else:
            return obj

    def to_json(self):
        # Convert to dict first
        data_dict = asdict(self)
        # Serialize any non-JSON-serializable objects
        serialized_dict = self.serialize_for_json(data_dict)
        try:
            return json.dumps(serialized_dict, ensure_ascii=False, indent=2)
        except UnicodeEncodeError as e:
            # Fallback: try with ASCII encoding if Unicode fails
            print(f"Warning: Unicode encoding failed, falling back to ASCII: {e}")
            return json.dumps(serialized_dict, ensure_ascii=True, indent=2)

    def save(self):
        """Save as a single JSON file"""
        os.makedirs(self.log_dir, exist_ok=True)
        timestamp = (
            self.start_time.replace(":", "-").replace(".", "-").replace(" ", "-")
        )

        filename = f"{self.log_dir}/task_{self.task_id}_{timestamp}.json"
        try:
            with open(filename, "w", encoding="utf-8") as f:
                f.write(self.to_json())
        except UnicodeEncodeError as e:
            # Fallback: try with different encoding if UTF-8 fails
            print(f"Warning: UTF-8 encoding failed, trying with system default: {e}")
            with open(filename, "w") as f:
                f.write(self.to_json())
        return filename

    @classmethod
    def from_dict(cls, d):
        return cls(**d)
