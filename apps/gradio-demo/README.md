# Local Deep Research Demo with Gradio Web UI

Host your own Deep Research demo using our [MiroThinker](https://huggingface.co/miromind-ai/MiroThinker-8B-DPO-v0.1) models and lightweight Gradio-based web interface.

## 🖥️ Hardware Requirement
- GPU: Nvidia 40xx/50xx series
- VRAM:
   -  8GB minimum (for 4B models), 16GB for longer context 
   -  16GB minimum (for 8B models), 24GB for longer context

## 📊 Performance Snapshot (M4 Pro and RTX 5070)

> Approx. tokens/sec (TPS), higher is better.

| Model | Quant | MacBook M4 Pro | RTX 5070 |
|---|---|---:|---:|
| MiroThinker-8B-SFT-v0.1-GGUF | Q2_K (2-bit) | ~24 | ~106 |
| MiroThinker-8B-SFT-v0.1-GGUF | Q4_K_M (4-bit) | ~24 | ~94 |
| MiroThinker-8B-SFT-v0.1-GGUF | Q8_0 (8-bit) | ~21 | ~64 |
| MiroThinker-14B-DPO-v0.1-GGUF | Q2_K (2-bit) | ~17 | ~63 |
| MiroThinker-14B-DPO-v0.1-GGUF | Q4_K_M (4-bit) | — | ~59 |


## 🚀 Quick Start

### 1. **Environment Setup**
   
   Copy the environment template to create your configuration:
   ```bash
   cp apps/miroflow-agent/.env.example apps/miroflow-agent/.env
   ```

   Edit the `apps/miroflow-agent/.env` file with your API keys:
   ```
   SERPER_API_KEY=your_serper_key
   E2B_API_KEY=your_e2b_key
   ```
#### Get your free API keys:
- [Serper](https://serper.dev/): 2,500 free search and scrape credits for new accounts
- [E2B](https://e2b.dev/): $100 free credits for new accounts


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
   uv run src/gradio_demo/main.py
   ```

### 5. **Access the Web Interface**

   Open your browser and navigate to: `http://localhost:8000`

## 📝 Notes
- Ensure your SGLang server is up and running before launching the demo
- The demo will use your local GPU for inference while leveraging external APIs for search and code execution
- Monitor your API usage through the respective provider dashboards
