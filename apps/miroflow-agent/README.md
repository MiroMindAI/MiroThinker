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

### Run a Single Task

The simplest way to test the agent is running `main.py` directly. It will execute a default task: *"What is the title of today's arxiv paper in computer science?"*

```bash
# Using MiroThinker models (requires your own model server)
uv run python main.py llm=qwen-3 agent=mirothinker_v1.5_keep5_max200 llm.base_url=http://localhost:61002/v1

# Using Claude (requires ANTHROPIC_API_KEY in .env)
uv run python main.py llm=claude-3-7 agent=single_agent_keep5

# Using GPT-5 (requires OPENAI_API_KEY in .env)
uv run python main.py llm=gpt-5 agent=single_agent_keep5
```

### Customize Your Task

To ask a different question, edit `main.py` line 32:

```python
task_description = "Your custom question here"
```

Then run the agent again. It will search the web, execute code, and provide an answer.

### Run Benchmark Evaluation

For systematic evaluation on standard benchmarks, add the `benchmark=` parameter:

```bash
# Run on debug benchmark (quick test)
uv run python main.py llm=qwen-3 agent=mirothinker_v1.5_keep5_max200 benchmark=debug llm.base_url=http://localhost:61002/v1

# Run on specific benchmarks
uv run python main.py llm=qwen-3 agent=mirothinker_v1.5_keep5_max200 benchmark=gaia-validation-text-103 llm.base_url=http://localhost:61002/v1
```

## Available Configurations

### LLM Models

| Model | Config Name | Requirements |
|-------|-------------|--------------|
| MiroThinker (self-hosted) | `qwen-3` | Model server + `llm.base_url` |
| Claude 3.7 Sonnet | `claude-3-7` | `ANTHROPIC_API_KEY` in .env |
| GPT-5 | `gpt-5` | `OPENAI_API_KEY` in .env |

### Agent Configurations

**MiroThinker v1.5:**

- `mirothinker_v1.5_keep5_max200` ⭐ (recommended) - context management, up to 200 turns
- `mirothinker_v1.5_keep5_max400` - context management, up to 400 turns (for BrowseComp)
- `mirothinker_v1.5` - no context management, up to 600 turns

**MiroThinker v1.0:**

- `mirothinker_v1.0_keep5` (recommended) - context management, up to 600 turns
- `mirothinker_v1.0` - no context management, up to 600 turns

**General (for closed-source models like Claude, GPT-5):**

- `single_agent_keep5` (recommended) - single agent with context management
- `single_agent` - single agent without context management

**Multi-Agent (Legacy for v0.1/v0.2):**

- `multi_agent` - multi-agent with commercial tools
- `multi_agent_os` - multi-agent with open-source tools

### Benchmark Configs

`debug`, `browsecomp`, `browsecomp_zh`, `hle`, `hle-text-2158`, `hle-text-500`, `gaia-validation-text-103`, `gaia-validation`, `frames`, `xbench_deepsearch`, `futurex`, `seal-0`, `aime2025`, `deepsearchqa`, `webwalkerqa`

## Output

The agent will:

1. Execute the task using available tools (search, code execution, etc.)
1. Generate a final summary and boxed answer
1. Save detailed logs to `../../logs/` directory
1. Display the results in the terminal

## Troubleshooting

| Problem | Solution |
|---------|----------|
| API key errors | Check `.env` file has correct keys |
| Model connection failed | Verify `llm.base_url` is accessible |
| Tool execution errors | Check E2B/Serper/Jina API keys and quotas |
| Out of memory | Use `mirothinker_v1.5_keep5_max200` config |

For detailed logs, check the `logs/` directory.
