# MiroFlow Agent

## Quick Start

The simplest way to run a case is using the default command:

```bash
# Run Claude-3.7-Sonnet with open-source tool set
uv run python main.py llm=claude-3-7 agent=evaluation_os benchmark=debug

# Run GPT-5 with open-source tool set
uv run python main.py llm=gpt-5 agent=evaluation_os benchmark=debug

# Use a different benchmark configuration
uv run python main.py llm=qwen-3 agent=evaluation_os benchmark=debug llm.openai_base_url=<base_url>
```

This will execute the default task: "What is the title of today's arxiv paper in computer science?"

## Available Configurations

- **LLM Models**: `claude-3-7`, `gpt-5`, `qwen-3`
- **Agent Configs**: `evaluation_os`, `evaluation`
- **Benchmark Configs**: `debug`, `browsecomp`, `frames`, etc.

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
