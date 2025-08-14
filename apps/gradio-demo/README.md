# Gradio Web UI Demo

A web interface demo built with Gradio for interactive AI applications.

## Quick Start

1. **Setup Environment Configuration**
   
   Copy the environment template to create your configuration:
   ```bash
   cp apps/miroflow-agent/.env.example apps/miroflow-agent/.env
   ```

2. **Install Dependencies**
   ```bash
   cd apps/gradio-demo
   uv sync
   ```

3. **Configure API Endpoint**
   
   Set your OpenAI API base URL:
   ```bash
   export OPENAI_BASE_URL=http://your-api-endpoint/v1
   ```

4. **Launch the Application**
   ```bash
   uv run src/gradio_demo/main.py
   ```

5. **Access the Web Interface**
   
   Open your browser and navigate to: `http://localhost:8000`
