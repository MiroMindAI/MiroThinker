# Local Deep Research Demo with Gradio Web UI

Host your own Deep Research demo using our [MiroThinker](https://huggingface.co/miromind-ai/MiroThinker-8B-DPO-v0.2) models and lightweight Gradio-based web interface.

<div align="center">
  <img src="https://github.com/MiroMindAI/miromindai.github.io/blob/assets/gif/MiroFlow-v0.1-deploy-4090.gif?raw=true" width="800" alt="MiroThinker Gradio Demo">
</div>

## 🖥️ Hardware Requirements

- **GPU**: NVIDIA RTX 40xx/50xx series or equivalent
- **VRAM**:
  - **8GB minimum** (for 4B models), **16GB recommended** for longer context processing
  - **16GB minimum** (for 8B models), **24GB recommended** for longer context processing
  - **32GB+ recommended** (for 14B/32B models) for optimal performance

## ⚙️ LLM Server Deployment

### Download Model Checkpoints

Download the full checkpoint from Hugging Face:

```python
from huggingface_hub import snapshot_download
snapshot_download(repo_id="miromind-ai/MiroThinker-8B-DPO-v0.2", local_dir="model/MiroThinker-8B-DPO")
```

### Option 1: SGLang Server (Recommended)

FP8 is a highly efficient 8-bit floating point format that significantly reduces memory usage while maintaining model quality. This approach provides excellent performance for inference workloads on modern GPUs.

Please install [SGLang](https://github.com/sgl-project/sglang) first. Then initilize fast inference with FP8 precision:

```bash
MODEL_PATH=model/MiroThinker-8B-DPO
QWEN3_NOTHINKING_TEMPLATE_PATH=assets/qwen3_nonthinking.jinja

python3 -m sglang.launch_server \
    --model-path $MODEL_PATH \
    --mem-fraction-static 0.9 \
    --quantization fp8 \
    --tp 1 \
    --dp 1 \
    --host 0.0.0.0 \
    --port 61005 \
    --trust-remote-code \
    --chat-template $QWEN3_NOTHINKING_TEMPLATE_PATH
```

It will start an openai compatible server with BASE_URL=`http://0.0.0.0:61005/v1`.

### Option 2: llama.cpp (Quantized)

For memory-efficient inference, download the pre-quantized GGUF version from the community:

**Note**: Thanks to the community for providing quantized versions: [mradermacher](https://huggingface.co/mradermacher)

```bash
# Download Q4_K_M quantized model (recommended balance)
wget https://huggingface.co/mradermacher/MiroThinker-8B-DPO-v0.2-GGUF/resolve/main/MiroThinker-8B-DPO-v0.2.Q4_K_M.gguf
```

Follow the [official llama.cpp installation guide](https://github.com/ggml-org/llama.cpp) to set up the environment. After that:

```bash
# Set up model and template paths
MODEL_PATH=model/MiroThinker-8B-DPO-v0.2.Q4_K_M.gguf
QWEN3_NOTHINKING_TEMPLATE_PATH=assets/qwen3_nonthinking.jinja

# Start the server
llama-server -m $MODEL_PATH \
    --port 61005 \
    -ngl 99 \
    -v \
    --jinja \
    --chat-template-file $QWEN3_NOTHINKING_TEMPLATE_PATH
```

This will start an OpenAI-compatible server at `http://0.0.0.0:61005/v1`.

### Other Options

You can also leverage other frameworks for model serving like Ollama, vLLM, and Text Generation Inference (TGI) for different deployment scenarios.

## 🚀 Quick Start Guide

### 1. **Environment Setup**

Get your free API keys:

- [Serper](https://serper.dev/): 2,500 free search credits for new accounts
- [Jina](https://jina.ai/reader): 10M free tokens for new accounts, scrape & extract clean text from any website, PDF, or online doc
- [E2B](https://e2b.dev/): $100 free credits for new accounts

Edit the `apps/miroflow-agent/.env` file with your API keys:

```
SERPER_API_KEY=your_serper_key
JINA_API_KEY=your_jina_key
E2B_API_KEY=your_e2b_key
```

### 2. **Install Dependencies**

We use [uv](https://github.com/astral-sh/uv) to manage all dependencies.

```bash
cd apps/gradio-demo
uv sync
```

### 3. **Configure API Endpoint**

Set your OpenAI API base URL as the SGLang endpoint:

```bash
export OPENAI_BASE_URL=http://your-sglang-address:your-sglang-port/v1
```

### 4. **Launch the Application**

```bash
DEMO_MODE=1 uv run main.py
```

### 5. **Access the Web Interface**

Open your browser and navigate to: `http://localhost:8000`

### 📝 Notes

- Ensure your LLM server is up and running before launching the demo
- The demo will use your local CPU/GPU for inference while leveraging external APIs for search and code execution
- Monitor your API usage through the respective provider dashboards

## 📊 Performance Benchmarks

> **Tokens per second (TPS)** - Higher values indicate better performance. Benchmarks conducted on consumer hardware.

| Model                    |     Quant      | MacBook M4 Pro  | RTX 5070  |
|:-------------------------|:--------------:|:---------------:|:---------:|
| MiroThinker-8B-SFT-v0.2  |  Q2_K (2-bit)  |     ~24 TPS     | ~106 TPS  |
| MiroThinker-8B-SFT-v0.2  | Q4_K_M (4-bit) |     ~24 TPS     |  ~94 TPS  |
| MiroThinker-8B-SFT-v0.2  |  Q8_0 (8-bit)  |     ~21 TPS     |  ~64 TPS  |
| MiroThinker-14B-DPO-v0.2 |  Q2_K (2-bit)  |     ~17 TPS     |  ~63 TPS  |
| MiroThinker-14B-DPO-v0.2 | Q4_K_M (4-bit) |        —        |  ~59 TPS  |

### Accuracy

We conducted experiments to evaluate the impact of FP8 precision on model performance. Under identical experimental settings, the original model and the FP8 quantized model produced comparable results on the GAIA validation set. These findings demonstrate that FP8 quantization does not negatively impact model performance.

For other quantization methods such as Q8_0, Q4_K_S, and Q4_K_M, they are optimized for CPU deployment to provide better user experience and faster inference speeds, though they may have some impact on model performance to varying degrees.
