# Contributing to MiroThinker

Thank you for your interest in contributing to MiroThinker! This document provides guidelines and instructions for contributing.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [How to Contribute](#how-to-contribute)
- [Pull Request Process](#pull-request-process)
- [Coding Standards](#coding-standards)
- [Running Tests](#running-tests)
- [Project Structure](#project-structure)

## Code of Conduct

Be respectful and inclusive. We welcome contributions from everyone.

## Getting Started

1. Fork the repository
2. Clone your fork:
   ```bash
   git clone https://github.com/YOUR_USERNAME/MiroThinker.git
   cd MiroThinker
   ```
3. Create a branch for your changes:
   ```bash
   git checkout -b your-feature-name
   ```

## Development Setup

### Prerequisites

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) package manager
- Git

### Installation

```bash
# Install dependencies for miroflow-agent
cd apps/miroflow-agent
uv sync

# Install dependencies for gradio-demo
cd ../gradio-demo
uv sync

# Install dependencies for libs
cd ../../libs/miroflow-tools
uv sync
```

### Environment Configuration

Copy the example environment file and configure your API keys:

```bash
cd apps/miroflow-agent
cp .env.example .env
# Edit .env with your API keys
```

Required keys for minimal setup:
- `SERPER_API_KEY` - Google search API
- `JINA_API_KEY` - Web scraping
- `E2B_API_KEY` - Code execution sandbox
- `SUMMARY_LLM_*` - LLM for content summarization

## How to Contribute

### Reporting Bugs

1. Check existing issues to avoid duplicates
2. Use a clear, descriptive title
3. Include:
   - Steps to reproduce
   - Expected behavior
   - Actual behavior
   - Environment details (OS, Python version, etc.)

### Suggesting Features

1. Open an issue with the "enhancement" label
2. Describe the feature and its use case
3. Explain why it would benefit the project

### Submitting Code

1. Create a feature branch
2. Make your changes
3. Add tests if applicable
4. Run tests and linting
5. Submit a pull request

## Pull Request Process

1. **Branch naming**: Use descriptive names like `fix/resource-cleanup` or `feat/add-api-endpoint`

2. **Commit messages**: Follow conventional commits:
   ```
   type(scope): description
   
   # Examples:
   fix(orchestrator): resolve state pollution on rollback
   feat(mcp): add support for SSE transport
   docs(readme): update installation instructions
   ```

3. **PR description**: Include:
   - Summary of changes
   - Related issue number (if any)
   - Testing performed
   - Screenshots (if applicable)

4. **Code review**: Address all review comments

5. **CI checks**: Ensure all tests pass

## Coding Standards

### Python Style

- Follow [PEP 8](https://peps.python.org/pep-0008/)
- Use type hints where appropriate
- Write docstrings for public functions and classes

### Code Formatting

We use [Ruff](https://github.com/astral-sh/ruff) for linting and formatting:

```bash
# Run linting
just lint

# Format code
just format

# Sort imports
just sort-imports

# Run all pre-commit checks
just precommit
```

### File Structure

```
apps/
├── miroflow-agent/     # Core agent logic
│   ├── src/
│   │   ├── core/       # Orchestrator, tool executor
│   │   ├── llm/        # LLM clients
│   │   └── utils/      # Utilities
│   └── tests/          # Unit tests
├── gradio-demo/        # Web UI
├── collect-trace/      # Trace collection
└── visualize-trace/    # Visualization tools

libs/
└── miroflow-tools/     # MCP tools library
```

## Running Tests

### Unit Tests

```bash
cd apps/miroflow-agent
uv run pytest tests/ -v
```

### Test Coverage

```bash
uv run pytest tests/ --cov=src --cov-report=html
```

### Running Specific Tests

```bash
# Run a specific test file
uv run pytest tests/test_orchestrator.py -v

# Run tests matching a pattern
uv run pytest tests/ -k "test_tool" -v
```

## Project Structure

| Directory | Description |
|-----------|-------------|
| `apps/miroflow-agent/` | Core agent framework |
| `apps/gradio-demo/` | Gradio web interface |
| `apps/collect-trace/` | Training trace collection |
| `apps/visualize-trace/` | Trace visualization |
| `apps/laravel-compatibility/` | LLM compatibility layer |
| `libs/miroflow-tools/` | MCP server tools |

## Getting Help

- 💬 [Discord](https://discord.com/invite/GPqEnkzQZd)
- 🐛 [GitHub Issues](https://github.com/MiroMindAI/MiroThinker/issues)
- 📖 [Documentation](https://github.com/MiroMindAI/MiroThinker#readme)

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

Thank you for contributing to MiroThinker! 🎉