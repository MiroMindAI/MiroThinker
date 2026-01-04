# MiroFlow Agent

> For comprehensive documentation, installation guide, and tool configuration, see the [main README](../../README.md).

## Prerequisites

Before running the agent, ensure you have:

1. **Installed dependencies**: Run `uv sync` in this directory
1. **Configured environment variables**: Copy `.env.example` to `.env` and fill in your API keys
   ```bash
   cp .env.example .env
   # Edit .env with your actual API keys (SERPER_API_KEY, JINA_API_KEY, E2B_API_KEY, etc.)
   ```
1. **Started your model server** (for MiroThinker models): See the [Serve the MiroThinker Model](../../README.md#serve-the-mirothinker-model) section

## Quick Start

The simplest way to run a case is using the default command:

```bash
# Run MiroThinker v1.5 with recommended configuration (context management, up to 200 turns)
uv run python main.py llm=qwen-3 agent=mirothinker_v1.5_keep5_max200 benchmark=debug llm.base_url=<base_url>

# Run MiroThinker v1.5 for BrowseComp benchmarks (context management, up to 400 turns)
uv run python main.py llm=qwen-3 agent=mirothinker_v1.5_keep5_max400 benchmark=debug llm.base_url=<base_url>

# Run MiroThinker v1.0 with context management
uv run python main.py llm=qwen-3 agent=mirothinker_v1.0_keep5 benchmark=debug llm.base_url=<base_url>

# Run Claude-3.7-Sonnet with single-agent configuration
uv run python main.py llm=claude-3-7 agent=single_agent_keep5 benchmark=debug

# Run GPT-5 with single-agent configuration
uv run python main.py llm=gpt-5 agent=single_agent_keep5 benchmark=debug
```

This will execute the default task: "What is the title of today's arxiv paper in computer science?"

## Available Configurations

- **LLM Models**: `claude-3-7`, `gpt-5`, `qwen-3`
- **Agent Configs (MiroThinker v1.5)**: `mirothinker_v1.5_keep5_max200` ⭐ (recommended), `mirothinker_v1.5_keep5_max400` (for BrowseComp), `mirothinker_v1.5`
- **Agent Configs (MiroThinker v1.0)**: `mirothinker_v1.0_keep5` (recommended), `mirothinker_v1.0`
- **Agent Configs (General)**: `single_agent`, `single_agent_keep5` (for closed-source models like Claude, GPT-5)
- **Agent Configs (Multi-Agent)**: `multi_agent`, `multi_agent_os`
- **Benchmark Configs**: `debug`, `browsecomp`, `browsecomp_zh`, `hle`, `hle-text-2158`, `gaia-validation-text-103`, `gaia-validation`, `frames`, `xbench_deepsearch`, `futurex`, `seal-0`, `aime2025`, `deepsearchqa`, etc.

### Customizing the Task

To change the task description, you need to modify the `main.py` file directly:

```python
# In main.py, change line 43:
task_description = "Your custom task here"
```

### Output

The agent will:

1. Execute the task using available tools
1. Generate a final summary and boxed answer
1. Save logs to `../../logs/debug/` directory
1. Display the results in the terminal

### Troubleshooting

- Make sure your API keys are set correctly
- Check the logs in the `logs/debug/` directory for detailed execution information
- Ensure all dependencies are installed with `uv sync`
