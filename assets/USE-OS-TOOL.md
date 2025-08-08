# USE-OS-TOOL for evaluation

We offer three tools which are designed as open-source alternatives to proprietary services, providing similar functionality while maintaining control over the underlying infrastructure and data processing.

The VQA and reasoning tools use the SILICONFLOW interface, which requires a SILICONFLOW API key (SILICONFLOW_API_KEY) to use. The audio tool, which leverages the OpenAI Whisper model, requires a URL and an API key (WHISPER_BASE_URL, WHISPER_API_KEY).

Please also refer to the agent configuration file: apps/miroflow-agent/conf/agent/evaluation_os.yaml

## Visual Question Answering Tool (`vision_mcp_server_os.py`)

**Tool Name:** `visual_question_answering`

**Description:** An open-source vision-language model service that answers questions about images using the Qwen2.5-VL-72B-Instruct model. This tool can analyze images from local files or URLs and provide detailed answers to questions about visual content. It supports common image formats (JPEG, PNG, GIF) and automatically encodes local images to base64 format for API transmission.

## Reasoning Tool (`reasoning_mcp_server_os.py`)

**Tool Name:** `reasoning`

**Description:** An open-source reasoning service designed for solving complex problems that require deep analytical thinking. This tool uses the DeepSeek-R1 model to tackle challenging mathematical problems, puzzles, riddles, and IQ test questions that demand extensive chain-of-thought reasoning. It's specifically designed for problems that require step-by-step logical analysis rather than simple or obvious questions.

## Audio Transcription Tool (`audio_mcp_server_os.py`)

**Tool Name:** `audio_transcription`

**Description:** An open-source audio transcription service that converts audio files to text using OpenAI's Whisper model. This tool can process both local audio files and audio files from URLs. It supports multiple audio formats including MP3, WAV, M4A, AAC, OGG, FLAC, and WMA. The tool automatically detects file formats, handles temporary file management, and provides robust error handling for network issues and invalid content types. It uses the "whisper-large-v3-turbo" model for high-quality transcription results.

**Tips for Deploy Whisper:**

1. download whisper-large-v3-turbo from Huggingface to /path/model/whisper
1. run the commands

```
   pip install vllm==0.10.0
   pip install vllm[audio]
   vllm serve /path/model/whisper --served-model-name whisper-large-v3-turbo --task transcription
```
