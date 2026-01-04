# Collect Trace

> TL;DR: Treat an RLVR-format dataset (Question + verifiable answer) as a benchmark. Run the evaluation pipeline; use LLM-as-a-Judge to verify correctness; then harvest the correct interaction traces as training data (for SFT / DPO).

## 📝 Overview

Collect Trace is a key component in the MiroThinker training pipeline. Instead of hand-curating training samples, it reuses RLVR datasets as test sets, and collects multi-turn interaction traces only from items judged correct.

Workflow:

1. Load each RLVR item’s question and verifiable answer.

1. Run the agent in the evaluation pipeline (with tool use / browsing as needed).

1. Verify the model's answer with an LLM-as-a-Judge against the RLVR reference answer.

1. Only for items judged correct, collect the full multi-turn trace and convert it into SFT / DPO-ready samples.

## 🚀 Quick Start

### Prerequisites

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) package manager
- OpenAI API key (for LLM-based validation)
- RLVR dataset (JSONL; contains question and a verifiable answer)

### Installation

1. **Navigate to the collect-trace directory**:

   ```bash
   cd apps/collect-trace
   ```

1. **Install dependencies**:

   ```bash
   uv sync
   ```

1. **Set up environment variables**:

   ```bash
   # Create .env if missing (safe; won't overwrite existing file)
   [ -f ../miroflow-agent/.env ] || cp ../miroflow-agent/.env.example ../miroflow-agent/.env
   # (Alternative on macOS/Linux) cp -n ../miroflow-agent/.env.example ../miroflow-agent/.env || true

   # Edit .env and fill in your keys
   # Required: OPENAI_API_KEY (for LLM-as-a-Judge)
   # Optional: other keys for specific tools
   ```

### Basic Usage

Run a benchmark evaluation to collect traces:

```bash
# Using Claude-3.7 for trace collection
bash scripts/collect_trace_claude37.sh

# Using GPT-5 for trace collection  
bash scripts/collect_trace_gpt5.sh

# Using Qwen-3 for trace collection  
bash scripts/collect_trace_qwen3.sh
```
