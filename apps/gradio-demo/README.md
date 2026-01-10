# Local Deep Research Demo with Gradio Web UI

Host your own Deep Research demo using our [MiroThinker v1.5](https://huggingface.co/miromind-ai/MiroThinker-v1.5-30B) models and lightweight Gradio-based web interface.

## 🖥️ Hardware Requirements

- **GPU**: NVIDIA RTX 40xx/50xx series or equivalent
- **VRAM**:
  - **16GB minimum** (with Q4 quantization via llama.cpp)
  - **48GB+ recommended** (for FP8 quantization or longer context)
  - MiroThinker-v1.5-30B is a 30B MoE model with 3B active parameters

## ⚙️ LLM Server Deployment

### Download Model Checkpoints

Download the full checkpoint from Hugging Face:

```python
from huggingface_hub import snapshot_download
snapshot_download(repo_id="miromind-ai/MiroThinker-v1.5-30B", local_dir="model/MiroThinker-v1.5-30B")
```

### Option 1: SGLang Server (Recommended)

FP8 is a highly efficient 8-bit floating point format that significantly reduces memory usage while maintaining model quality. This approach provides excellent performance for inference workloads on modern GPUs.

Please install [SGLang](https://github.com/sgl-project/sglang) first. Then initialize fast inference with FP8 precision:

```bash
MODEL_PATH=model/MiroThinker-v1.5-30B

python3 -m sglang.launch_server \
    --model-path $MODEL_PATH \
    --mem-fraction-static 0.9 \
    --quantization fp8 \
    --tp 1 \
    --dp 1 \
    --host 0.0.0.0 \
    --port 61005 \
    --trust-remote-code
```

It will start an openai compatible server with BASE_URL=`http://0.0.0.0:61005/v1`.

### Option 2: llama.cpp (Quantized)

For memory-efficient inference, download the pre-quantized GGUF version from the community:

**Note**: Thanks to the community for providing quantized versions: [mradermacher](https://huggingface.co/mradermacher)

```bash
# Download Q4_K_M quantized model (recommended balance)
wget https://huggingface.co/mradermacher/MiroThinker-v1.5-30B-GGUF/resolve/main/MiroThinker-v1.5-30B.Q4_K_M.gguf
```

Follow the [official llama.cpp installation guide](https://github.com/ggml-org/llama.cpp) to set up the environment. After that:

```bash
# Set up model path
MODEL_PATH=model/MiroThinker-v1.5-30B.Q4_K_M.gguf

# Start the server
llama-server -m $MODEL_PATH \
    --port 61005 \
    -ngl 99 \
    -v
```

This will start an OpenAI-compatible server at `http://0.0.0.0:61005/v1`.

### Other Options

You can also leverage other frameworks for model serving like Ollama, vLLM, and Text Generation Inference (TGI) for different deployment scenarios.

## 🚀 Quick Start Guide

### 1. **Environment Setup**

Get your API keys:

- [Serper](https://serper.dev/): 2,500 free search credits for new accounts (required for web search)
- [E2B](https://e2b.dev/): Free tier available (required for Python code execution)
- [Jina](https://jina.ai/): Free tier available (required for web scraping)

Edit the `apps/miroflow-agent/.env` file with your API keys:

```bash
# Required - Web Search
SERPER_API_KEY=your_serper_key

# Required - Python Code Execution (E2B Cloud Sandbox)
E2B_API_KEY=your_e2b_key

# Required - Web Scraping
JINA_API_KEY=your_jina_key

# Required - Summary LLM (for webpage summarization)
# Option 1: Use OpenAI GPT-5-Nano (recommended, cost-effective)
SUMMARY_LLM_BASE_URL=https://api.openai.com/v1
SUMMARY_LLM_MODEL_NAME=gpt-5-nano
SUMMARY_LLM_API_KEY=your_openai_key

# Option 2: Use MiroThinker itself (if you have enough VRAM)
# SUMMARY_LLM_BASE_URL=http://0.0.0.0:61005/v1
# SUMMARY_LLM_MODEL_NAME=MiroThinker
# SUMMARY_LLM_API_KEY=none
```

### 2. **Install Dependencies**

We use [uv](https://github.com/astral-sh/uv) to manage all dependencies.

```bash
cd apps/gradio-demo
uv sync
```

### 3. **Configure API Endpoint**

Set your LLM API endpoint and API key:

```bash
export BASE_URL=http://your-sglang-address:your-sglang-port/v1
export API_KEY=your_api_key  # Optional, required if your endpoint needs authentication
```

### 4. **Launch the Application**

```bash
uv run main.py
```

### 5. **Access the Web Interface**

Open your browser and navigate to: `http://localhost:8080`

### 📝 Notes

- Ensure your LLM server is up and running before launching the demo
- The demo will use your local CPU/GPU for inference while leveraging external APIs for search and code execution
- Monitor your API usage through the respective provider dashboards
