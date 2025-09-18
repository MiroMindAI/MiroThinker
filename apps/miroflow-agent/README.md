# MiroFlow Agent

## Quick Start

### Prerequisites

1. Install uv: https://docs.astral.sh/uv/getting-started/installation/
1. Set up your API keys in environment variables:
   ```bash
   export ANTHROPIC_API_KEY="your-anthropic-key"
   # or
   export OPENAI_API_KEY="your-openai-key"
   ```

### Run a Simple Case

The simplest way to run a case is using the default configuration:

```bash
uv run python main.py
```

This will execute the default task: "What is the title of today's arxiv paper in computer science?"

### Run with Custom Configuration

You can override the default configuration using Hydra's override syntax:

```bash
# Use a different LLM model
uv run python main.py llm=claude-3-7

# Use a different agent configuration  
uv run python main.py agent=evaluation

# Use a different benchmark configuration
uv run python main.py benchmark=debug
```

### Available Configurations

- **LLM Models**: `claude-3-7`, `gpt-5`, `qwen-3`
- **Agent Configs**: `evaluation`, `evaluation_os`
- **Benchmark Configs**: `default`, `debug`, `browsecomp`, `frames`, etc.

### Example Commands

```bash
# Run with Claude 3.7 Sonnet
uv run python main.py llm=claude-3-7

# Run with GPT-5
uv run python main.py llm=gpt-5

# Run with evaluation configuration
uv run python main.py agent=evaluation

# Run with debug benchmark configuration
uv run python main.py benchmark=debug
```

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
