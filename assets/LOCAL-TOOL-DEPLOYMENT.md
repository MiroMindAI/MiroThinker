# Local Tool Deployment Guide

This guide explains how to deploy open-source tools locally for use with MiroThinker. These tools are optional enhancements that can replace commercial alternatives in your agent configuration.

## Overview

MiroThinker supports several optional open-source tools that you can deploy locally:

- **Audio Transcription**: Whisper-Large-v3-Turbo for transcribing audio files
- **Visual Question Answering**: Qwen2.5-VL-72B-Instruct for answering questions about images
- **Reasoning Engine**: Qwen3-235B-A22B-Thinking-2507 for complex reasoning tasks

These tools are used when you configure your agent with `tool-transcribe-os`, `tool-vqa-os`, or `tool-reasoning-os` in your agent configuration file.

## Prerequisites

- **GPU**: NVIDIA GPU with sufficient VRAM
- **Python 3.10+**
- **CUDA**: Compatible CUDA toolkit installed
- **Model Storage**: Sufficient disk space to download model checkpoints

## Tool Deployment

### 1. Audio Transcription Tool (`tool-transcribe-os`)

**Model**: [Whisper-Large-v3-Turbo](https://huggingface.co/openai/whisper-large-v3-turbo)

**Description**: Transcribes audio files (MP3, WAV, M4A, AAC, OGG, FLAC, WMA) to text. Supports both local files and remote URLs.

**Deployment with vLLM**:

```bash
# Install vLLM with audio support
pip install vllm==0.10.0
pip install vllm[audio]

# Start the server
vllm serve openai/whisper-large-v3-turbo \
  --served-model-name whisper-large-v3-turbo \
  --task transcription \
  --host 0.0.0.0 \
  --port 8000
```

**Configuration in `.env`**:

```bash
WHISPER_MODEL_NAME="openai/whisper-large-v3-turbo"
WHISPER_API_KEY=your_api_key  # Optional, if your server requires authentication
WHISPER_BASE_URL="http://0.0.0.0:8000/v1"
```

### 2. Visual Question Answering Tool (`tool-vqa-os`)

**Model**: [Qwen2.5-VL-72B-Instruct](https://huggingface.co/Qwen/Qwen2.5-VL-72B-Instruct)

**Description**: Answers questions about images. Supports local image files and URLs. Automatically encodes local images to Base64 for API requests. Compatible with JPEG, PNG, GIF formats.

**Deployment with SGLang**:

```bash
# Install SGLang
pip install sglang[all]

# Start the server
python3 -m sglang.launch_server \
  --model-path Qwen/Qwen2.5-VL-72B-Instruct \
  --tp 8 \
  --host 0.0.0.0 \
  --port 8001 \
  --trust-remote-code \
  --enable-metrics
```

**Configuration in `.env`**:

```bash
VISION_MODEL_NAME="Qwen/Qwen2.5-VL-72B-Instruct"
VISION_API_KEY=your_api_key  # Optional, if your server requires authentication
VISION_BASE_URL="http://0.0.0.0:8001/v1/chat/completions"
```

### 3. Reasoning Engine Tool (`tool-reasoning-os`)

**Model**: [Qwen3-235B-A22B-Thinking-2507](https://huggingface.co/Qwen/Qwen3-235B-A22B-Thinking-2507)

**Description**: A reasoning service for solving complex analytical problems, such as advanced mathematics, puzzles, and riddles. Supports long-context reasoning tasks (up to 131K tokens).

**Deployment with SGLang**:

```bash
# Install SGLang
pip install sglang[all]

# Start the server
python3 -m sglang.launch_server \
  --model-path Qwen/Qwen3-235B-A22B-Thinking-2507 \
  --tp 8 \
  --host 0.0.0.0 \
  --port 8002 \
  --trust-remote-code \
  --context-length 131072 \
  --enable-metrics
```

**Configuration in `.env`**:

```bash
REASONING_MODEL_NAME="Qwen/Qwen3-235B-A22B-Thinking-2507"
REASONING_API_KEY=your_api_key  # Optional, if your server requires authentication
REASONING_BASE_URL="http://0.0.0.0:8002/v1/chat/completions"
```

## Using Deployed Tools

Once you have deployed the tools, configure your agent to use them:

1. **Edit your agent configuration** (e.g., `apps/miroflow-agent/conf/agent/my_custom_config.yaml`):

```yaml
main_agent:
  tools:
    - tool-python
    - search_and_scrape_webpage
    - jina_scrape_llm_summary
    - tool-transcribe-os    # Use local Whisper deployment
    - tool-vqa-os           # Use local Qwen2.5-VL deployment
    - tool-reasoning-os     # Use local Qwen3-235B deployment
  max_turns: 400
```

2. **Configure environment variables** in `apps/miroflow-agent/.env` as shown in each tool's deployment section above.

1. **Run your agent**:

```bash
cd apps/miroflow-agent
uv run main.py llm=qwen-3 agent=my_custom_config llm.base_url=https://your_base_url/v1
```

## Commercial Alternatives

If you prefer not to deploy these tools locally, you can use commercial alternatives:

- **`tool-transcribe`**: Uses OpenAI's GPT-4o mini Transcribe API
- **`tool-vqa`**: Uses Claude Sonnet 3.7 API
- **`tool-reasoning`**: Uses Claude Sonnet 3.7 API

Simply replace `-os` versions with commercial versions in your agent configuration and configure the corresponding API keys (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`).

## Additional Resources

- **SGLang Documentation**: [https://sglang.readthedocs.io/](https://sglang.readthedocs.io/)
- **vLLM Documentation**: [https://docs.vllm.ai/](https://docs.vllm.ai/)
- **Model Cards**: Check HuggingFace model pages for specific requirements and recommendations
