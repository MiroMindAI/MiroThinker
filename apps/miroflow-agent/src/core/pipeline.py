# Copyright (c) 2025 MiroMind
# This source code is licensed under the MIT License.


import traceback
import uuid
from typing import Any, Dict, List, Optional

from miroflow_tools.manager import ToolManager
from omegaconf import DictConfig

from ..config.settings import (
    create_mcp_server_parameters,
    get_env_info,
)
from ..io.output_formatter import OutputFormatter
from ..llm.factory import ClientFactory
from ..logging.task_logger import (
    TaskLog,
    get_utc_plus_8_time,
)
from .orchestrator import Orchestrator


async def execute_task_pipeline(
    cfg: DictConfig,
    task_id: str,
    task_description: str,
    task_file_name: str,
    main_agent_tool_manager: ToolManager,
    sub_agent_tool_managers: List[Dict[str, ToolManager]],
    output_formatter: OutputFormatter,
    ground_truth: Optional[Any] = None,
    log_dir: str = "logs",
    stream_queue: Optional[Any] = None,
    tool_definitions: Optional[List[Dict[str, Any]]] = None,
    sub_agent_tool_definitions: Optional[Dict[str, List[Dict[str, Any]]]] = None,
):
    """
    Executes the full pipeline for a single task.

    Args:
        cfg: The Hydra configuration object.
        task_description: The description of the task for the LLM.
        task_file_name: The path to an associated file (optional).
        task_id: A unique identifier for this task run (used for logging).
        main_agent_tool_manager: An initialized main agent ToolManager instance.
        sub_agent_tool_managers: A dictionary of initialized sub-agent ToolManager instances.
        output_formatter: An initialized OutputFormatter instance.
        ground_truth: The ground truth for the task (optional).
        log_dir: The directory to save the task log (default: "logs").
        stream_queue: A queue for streaming the task execution (optional).
        tool_definitions: The definitions of the tools for the main agent (optional).
        sub_agent_tool_definitions: The definitions of the tools for the sub-agents (optional).
    Returns:
        A tuple containing:
        - A string with the final execution log and summary, or an error message.
        - The final boxed answer.
        - The path to the log file.
    """
    # Create task log
    task_log = TaskLog(
        log_dir=log_dir,
        task_id=task_id,
        start_time=get_utc_plus_8_time(),
        input={"task_description": task_description, "task_file_name": task_file_name},
        env_info=get_env_info(cfg),
        ground_truth=ground_truth,
    )

    # Log task start
    task_log.log_step(
        "info", "Main | Task Start", f"--- Starting Task Execution: {task_id} ---"
    )

    # Set task_log for all ToolManager instances
    main_agent_tool_manager.set_task_log(task_log)
    if sub_agent_tool_managers:
        for sub_agent_tool_manager in sub_agent_tool_managers.values():
            sub_agent_tool_manager.set_task_log(task_log)

    try:
        # Initialize LLM client
        random_uuid = str(uuid.uuid4())
        unique_id = f"{task_id}-{random_uuid}"
        llm_client = ClientFactory(task_id=unique_id, cfg=cfg, task_log=task_log)

        # Initialize orchestrator
        orchestrator = Orchestrator(
            main_agent_tool_manager=main_agent_tool_manager,
            sub_agent_tool_managers=sub_agent_tool_managers,
            llm_client=llm_client,
            output_formatter=output_formatter,
            cfg=cfg,
            task_log=task_log,
            stream_queue=stream_queue,
            tool_definitions=tool_definitions,
            sub_agent_tool_definitions=sub_agent_tool_definitions,
        )

        (
            final_summary,
            final_boxed_answer,
            failure_experience_summary,
        ) = await orchestrator.run_main_agent(
            task_description=task_description,
            task_file_name=task_file_name,
            task_id=task_id,
        )

        llm_client.close()

        task_log.final_boxed_answer = final_boxed_answer
        task_log.status = "success"

        # Store failure experience summary in task log if available
        if failure_experience_summary:
            task_log.trace_data["failure_experience_summary"] = (
                failure_experience_summary
            )

        log_file_path = task_log.save()
        return (
            final_summary,
            final_boxed_answer,
            log_file_path,
            failure_experience_summary,
        )

    except Exception as e:
        error_details = traceback.format_exc()
        task_log.log_step(
            "warning",
            "task_error_notification",
            f"An error occurred during task {task_id}",
        )
        task_log.log_step("error", "task_error_details", error_details)

        error_message = (
            f"Error executing task {task_id}:\n"
            f"Description: {task_description}\n"
            f"File: {task_file_name}\n"
            f"Error Type: {type(e).__name__}\n"
            f"Error Details:\n{error_details}"
        )

        task_log.status = "failed"
        task_log.error = error_details

        log_file_path = task_log.save()

        return error_message, "", log_file_path, None

    finally:
        task_log.end_time = get_utc_plus_8_time()

        # Record task summary to structured log
        task_log.log_step(
            "info",
            "task_execution_finished",
            f"Task {task_id} execution completed with status: {task_log.status}",
        )
        task_log.save()


def create_pipeline_components(cfg: DictConfig):
    """
    Creates and initializes the core components of the agent pipeline.

    Args:
        cfg: The Hydra configuration object.

    Returns:
        Tuple of (main_agent_tool_manager, sub_agent_tool_managers, output_formatter)
    """
    # Create ToolManagers for main agent and sub-agents
    main_agent_mcp_server_configs, main_agent_blacklist = create_mcp_server_parameters(
        cfg, cfg.agent.main_agent
    )
    main_agent_tool_manager = ToolManager(
        main_agent_mcp_server_configs,
        tool_blacklist=main_agent_blacklist,
    )

    # Create OutputFormatter
    output_formatter = OutputFormatter()
    sub_agent_tool_managers = {}

    # For single agent mode
    if not cfg.agent.sub_agents:
        return main_agent_tool_manager, {}, output_formatter

    for sub_agent in cfg.agent.sub_agents:
        sub_agent_mcp_server_configs, sub_agent_blacklist = (
            create_mcp_server_parameters(cfg, cfg.agent.sub_agents[sub_agent])
        )
        sub_agent_tool_manager = ToolManager(
            sub_agent_mcp_server_configs,
            tool_blacklist=sub_agent_blacklist,
        )
        sub_agent_tool_managers[sub_agent] = sub_agent_tool_manager

    return main_agent_tool_manager, sub_agent_tool_managers, output_formatter
