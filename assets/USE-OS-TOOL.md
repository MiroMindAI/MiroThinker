# USE-OS-TOOL for Evaluation

This project supports **two tool configuration modes** for benchmark testing:

1. **Default Setting with Open-Source Tools** — Uses open-source tools as much as possible.
   *Config file:* [`evaluation_os.yaml`](../apps/miroflow-agent/conf/agent/evaluation_os.yaml)

2. **Advanced Setting with Commercial Tools** — Uses commercial tools with advanced features.
   *Config file:* [`evaluation.yaml`](../apps/miroflow-agent/conf/agent/evaluation.yaml)

## Tool List

|         Tool Set          |                         Default Setting<br>with Open-Source Tools                          |                        Advanced Setting<br>with Commercial Tools                         |
| :-----------------------: |:------------------------------------------------------------------------------------------:|:----------------------------------------------------------------------------------------:|
|       Google Search       |                               [Serper](https://serper.dev/)                                |                              [Serper](https://serper.dev/)                               |
|       Linux Sandbox       |                                  [E2B](https://e2b.dev/)                                   |                                 [E2B](https://e2b.dev/)                                  |
|    Audio Transcription    |       [Whisper-Large-v3-Turbo](https://huggingface.co/openai/whisper-large-v3-turbo)       | [GPT-4o mini Transcribe](https://platform.openai.com/docs/models/gpt-4o-mini-transcribe) |
| Visual Question Answering |       [Qwen2.5-VL-72B-Instruct](https://huggingface.co/Qwen/Qwen2.5-VL-72B-Instruct)       |   [Claude Sonnet 3.7](https://docs.anthropic.com/en/docs/about-claude/models/overview)   |
|         Reasoning         | [Qwen3-235B-A22B-Thinking-2507](https://huggingface.co/Qwen/Qwen3-235B-A22B-Thinking-2507) |   [Claude Sonnet 3.7](https://docs.anthropic.com/en/docs/about-claude/models/overview)   |

## Environment Variables

Configure the following variables in your `apps/miroflow-agent/.env` file according to the mode you choose:

```python
# API for Google Search (recommended)
SERPER_API_KEY=your_serper_key
SERPER_BASE_URL="https://google.serper.dev"

# API for Web Scraping (recommended)
JINA_API_KEY=your_jina_key
JINA_BASE_URL="https://r.jina.ai"

# API for Linux Sandbox (recommended)
E2B_API_KEY=your_e2b_key

# API for LLM-as-Judge (for benchmark testing, optional)
OPENAI_API_KEY=your_openai_key

# API for Open-Source Audio Transcription Tool (for benchmark testing, optional)
WHISPER_MODEL_NAME="openai/whisper-large-v3-turbo"
WHISPER_API_KEY=your_whisper_key
WHISPER_BASE_URL="https://your_whisper_base_url/v1"

# API for Open-Source VQA Tool (for benchmark testing, optional)
VISION_MODEL_NAME="Qwen/Qwen2.5-VL-72B-Instruct"
VISION_API_KEY=your_vision_key
VISION_BASE_URL="https://your_vision_base_url/v1/chat/completions"

# API for Open-Source Reasoning Tool (for benchmark testing, optional)
REASONING_MODEL_NAME="Qwen/Qwen3-235B-A22B-Thinking-2507"
REASONING_API_KEY=your_reasoning_key
REASONING_BASE_URL="https://your_reasoning_base_url/v1/chat/completions"

# API for Claude Sonnet 3.7 as Commercial Tools (optional)
ANTHROPIC_API_KEY=your_anthropic_key

# API for Sougou Search (optional)
TENCENTCLOUD_SECRET_ID=your_tencent_cloud_secret_id
TENCENTCLOUD_SECRET_KEY=your_tencent_cloud_secret_key
```

## Tool Descriptions and Deployment

### 1. Visual Question Answering Tool

**Tool Name:** `visual_question_answering`

**Description:**
An open-source vision-language model service that answers questions about images.
Supports local image files and URLs. Automatically encodes local images to Base64 for API requests. Compatible with JPEG, PNG, GIF formats.

* **Open-Source Mode:** Qwen2.5-VL-72B-Instruct
* **Commercial Mode:** Claude Sonnet 3.7

**Local Deployment (Open-Source Mode):**

```bash
python3 -m sglang.launch_server \
  --model-path /path/to/Qwen2.5-VL-72B-Instruct \
  --tp 8 --host 0.0.0.0 --port 1234 \
  --trust-remote-code --enable-metrics \
  --log-level debug --log-level-http debug \
  --log-requests --log-requests-level 2 --show-time-cost
```

### 2. Reasoning Tool

**Tool Name:** `reasoning`

**Description:**
A reasoning service for solving complex analytical problems, such as advanced mathematics, puzzles, and riddles.

* **Open-Source Mode:** Qwen3-235B-A22B-Thinking-2507
* **Commercial Mode:** Claude Sonnet 3.7

**Local Deployment (Open-Source Mode):**

```bash
python3 -m sglang.launch_server \
  --model-path /path/to/Qwen3-235B-A22B-Thinking-2507 \
  --tp 8 --host 0.0.0.0 --port 1234 \
  --trust-remote-code --enable-metrics \
  --log-level debug --log-level-http debug \
  --log-requests --log-requests-level 2 \
  --show-time-cost --context-length 131072
```

### 3. Audio Transcription Tool

**Tool Name:** `audio_transcription`

**Description:**
A transcription service converts audio files to text.
Supports MP3, WAV, M4A, AAC, OGG, FLAC, and WMA formats. Can process both local and remote audio. Includes format detection, temporary file handling, and robust error handling.

* **Open-Source Mode:** Whisper-Large-v3-Turbo
* **Commercial Mode:** GPT-4o mini Transcribe

**Local Deployment (Open-Source Mode):**

```bash
pip install vllm==0.10.0
pip install vllm[audio]
vllm serve /path/to/whisper \
  --served-model-name whisper-large-v3-turbo \
  --task transcription
```
