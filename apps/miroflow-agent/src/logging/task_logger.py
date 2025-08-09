# Copyright 2025 Miromind.ai
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger()


def bootstrap_logger() -> logging.Logger:
    """Configure the miroflow_agent logger to print filename and line number"""

    # Configure only miroflow_agent logger, not the root logger
    miroflow_logger = logging.getLogger()

    # Create our desired formatter
    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Remove any existing handlers to ensure consistent configuration
    for handler in miroflow_logger.handlers[:]:
        miroflow_logger.removeHandler(handler)

    # Add our handler with the specified formatter
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    # Configure only miroflow_agent logger, not the root logger
    miroflow_logger = logging.getLogger()
    miroflow_logger.setLevel(logging.INFO)
    # miroflow_logger.setLevel(logging.DEBUG)
    miroflow_logger.addHandler(handler)
    miroflow_logger.setLevel(logging.DEBUG)

    return miroflow_logger


def get_utc_plus_8_time() -> str:
    """Get UTC+8 timezone current time string"""
    utc_plus_8 = timezone(timedelta(hours=8))
    return datetime.now(utc_plus_8).strftime("%Y-%m-%d %H:%M:%S")


def get_utc_plus_8_time_z_format() -> str:
    """Get UTC+8 time in Z format string for backward compatibility"""
    utc_plus_8_tz = timezone(timedelta(hours=8))
    return datetime.now(utc_plus_8_tz).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


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
    status: str = "info"  # "info", "warning", "error", "success", "debug"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskLog:
    status: str = "running"
    start_time: str = ""
    end_time: str = ""

    task_original_name: str = ""
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
            f"sub_{sub_agent_name}_session_start",
            f"Starting {session_id} for subtask: {subtask_description[:100]}{'...' if len(subtask_description) > 100 else ''}",
            "info",
            metadata={"session_id": session_id, "subtask": subtask_description},
        )

        return session_id

    def end_sub_agent_session(self, sub_agent_name: str) -> Optional[str]:
        """End the current sub-agent session"""
        self.log_step(
            f"sub_{sub_agent_name}_session_end",
            f"Ending {self.current_sub_agent_session_id}",
            "success",
            metadata={"session_id": self.current_sub_agent_session_id},
        )
        self.current_sub_agent_session_id = None
        return None

    def log_step(
        self,
        step_name: str,
        message: str,
        status: str = "info",
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """Record execution step"""
        step_log = StepLog(
            step_name=step_name,
            message=message,
            timestamp=get_utc_plus_8_time(),
            status=status,
            metadata=metadata or {},
        )

        self.step_logs.append(step_log)

        # Also print to console
        logger.info(f"[{status.upper()}] {step_name}: {message}")

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
        return json.dumps(serialized_dict, ensure_ascii=False, indent=2)

    def save(self):
        """Save as a single JSON file"""
        os.makedirs(self.log_dir, exist_ok=True)
        timestamp = self.start_time.replace(":", "-").replace(".", "-")
        filename = f"{self.log_dir}/task_{self.task_id}_{timestamp}.json"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(self.to_json())
        return filename

    @classmethod
    def from_dict(cls, d):
        return cls(**d)
